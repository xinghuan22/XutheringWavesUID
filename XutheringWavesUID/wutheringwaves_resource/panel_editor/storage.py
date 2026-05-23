"""路径/缩略图/列表 — 面板编辑器后端的文件层。"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from PIL import Image

from gsuid_core.logger import logger

from ...utils import name_convert
from ...utils.name_convert import easy_id_to_name
from ...utils.resource.RESOURCE_PATH import (
    BAKE_PATH,
    CUSTOM_DIRS as TYPE_PATHS,
    IMAGE_EXTS,
    MAIN_PATH,
)
# 整个插件 SHA256[:8] 唯一实现; 也兼做临时上传 token 的随机化后缀。
from ...wutheringwaves_charinfo.card_hash_index import compute_hash as hash_id_for


# 严格白名单, 防止 char_id / token 触发路径穿越或越权写入。
# 文件名 (name) 由历史 / 第三方写入, 可能含中文; 仅拒路径分隔符/NUL/控制字符,
# 配合 safe_join 的 relative_to 兜底, 路径穿越无可乘之机。
_SAFE_CHAR_ID = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_NAME_FORBID = re.compile(r"[\x00-\x1f/\\]")  # 控制字符 + 正反斜杠


def is_safe_char_id(s: object) -> bool:
    return isinstance(s, str) and bool(_SAFE_CHAR_ID.match(s))


def is_safe_name(s: object) -> bool:
    if not isinstance(s, str):
        return False
    if not s or len(s) > 256:
        return False
    if s in {".", ".."} or s.startswith("."):
        return False
    return _NAME_FORBID.search(s) is None


def is_safe_token(s: object) -> bool:
    return isinstance(s, str) and bool(_SAFE_TOKEN.match(s))


# 临时上传与裁剪原图保存目录
PANEL_EDIT_TMP = MAIN_PATH / "panel_edit_tmp"
PANEL_EDIT_TMP.mkdir(parents=True, exist_ok=True)

# 缩略图缓存目录
PANEL_EDIT_THUMBS = BAKE_PATH / "panel_edit_thumbs"
PANEL_EDIT_THUMBS.mkdir(parents=True, exist_ok=True)


def is_valid_type(t: str) -> bool:
    return t in TYPE_PATHS


def base_dir_for(t: str) -> Path:
    return TYPE_PATHS[t]


def char_dir_for(t: str, char_id: str) -> Path:
    return base_dir_for(t) / char_id


def safe_join(base: Path, *parts: str) -> Optional[Path]:
    """把 parts 拼到 base, 拒绝越权路径。

    注意: 调用前 base 必须是已知的安全根目录, 不要传入用户控制的 base。
    parts 中的任意分隔符或 .. 都会触发拒绝。
    """
    base_resolved = base.resolve()
    for p in parts:
        if not isinstance(p, str) or not p:
            return None
        if "/" in p or "\\" in p or p in {".", ".."}:
            return None
    try:
        candidate = base_resolved.joinpath(*parts).resolve()
    except Exception:
        return None
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate


def safe_target_image(t: str, char_id: str, name: str) -> Optional[Path]:
    """type+char_id+name 一站式解析, 三层都受白名单保护。"""
    if not is_valid_type(t):
        return None
    if not is_safe_char_id(char_id) or not is_safe_name(name):
        return None
    return safe_join(base_dir_for(t), char_id, name)


def safe_char_dir(t: str, char_id: str) -> Optional[Path]:
    if not is_valid_type(t):
        return None
    if not is_safe_char_id(char_id):
        return None
    return safe_join(base_dir_for(t), char_id)


def iter_images(path: Path) -> Iterable[Path]:
    if not path.is_dir():
        return
    for p in sorted(path.iterdir(), key=lambda p: p.name):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            yield p


def _is_char_id(s: str) -> bool:
    """角色 id 一律 4 位纯数字; id2name 里武器/声骸/链等的 key 不符合此规则。"""
    return isinstance(s, str) and len(s) == 4 and s.isdigit()


def list_folders(t: str) -> List[dict]:
    """列出目标类型下所有合法角色条目。

    - 磁盘上有目录的: 真实 count
    - id2name 里有但磁盘没目录的: 合成 count=0 占位 (上传时 mkdir 会自动建)
    - 非 4 位纯数字命名的目录: 忽略 (非角色或历史脏数据)
    """
    base = base_dir_for(t)
    seen: dict = {}

    if base.exists():
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if not d.is_dir() or not _is_char_id(d.name):
                continue
            seen[d.name] = {
                "char_id": d.name,
                "char_name": easy_id_to_name(d.name, d.name),
                "count": sum(1 for _ in iter_images(d)),
            }

    try:
        name_convert.ensure_data_loaded()
        for char_id in name_convert.id2name.keys():
            if char_id in seen or not _is_char_id(char_id):
                continue
            seen[char_id] = {
                "char_id": char_id,
                "char_name": easy_id_to_name(char_id, char_id),
                "count": 0,
            }
    except Exception as e:
        logger.debug(f"[鸣潮·面板编辑] id2name 合并跳过: {e}")

    return sorted(seen.values(), key=lambda x: x["char_id"])


def list_images(t: str, char_id: str) -> List[dict]:
    folder = char_dir_for(t, char_id)
    items = []
    for p in iter_images(folder):
        info = p.stat()
        items.append(
            {
                "name": p.name,
                "hash_id": hash_id_for(p.name),
                "size": info.st_size,
                "mtime": int(info.st_mtime),
            }
        )
    return items


# 缩略图按"角色卡实际显示区"裁剪的版本号; 改裁剪逻辑时 +1 使旧缓存失效。
_THUMB_VERSION = 2

# card 自定义图经 contain 缩放居中进 PANEL_OUT, 仅 PANEL_VIS 窗口在角色卡可见
# (与 card_utils._PANEL_VISIBLE_BOX_LOCAL / 前端 app.js panelVisibleRectInCrop 对齐)。
_PANEL_OUT = (560, 1000)
_PANEL_VIS = (60, 95, 500, 900)
# stamina/MR 卡背景容器 (stamina_card.html .container), bg 以 object-fit:cover 居中填充。
_BG_DISPLAY_RATIO = 1150 / 850


def _panel_visible_box(w: int, h: int) -> Optional[Tuple[int, int, int, int]]:
    if w <= 0 or h <= 0:
        return None
    ow, oh = _PANEL_OUT
    l0, t0, r0, b0 = _PANEL_VIS
    f = (ow / w) if w > h else (oh / h)
    px = (ow - w * f) / 2
    py = (oh - h * f) / 2
    l = max(0.0, min((l0 - px) / f, w))
    t = max(0.0, min((t0 - py) / f, h))
    r = max(0.0, min((r0 - px) / f, w))
    b = max(0.0, min((b0 - py) / f, h))
    if r <= l or b <= t:
        return None
    return round(l), round(t), round(r), round(b)


def _cover_box(w: int, h: int, ratio: float) -> Optional[Tuple[int, int, int, int]]:
    if w <= 0 or h <= 0:
        return None
    if w / h > ratio:
        nw = round(h * ratio)
        x0 = (w - nw) // 2
        return x0, 0, x0 + nw, h
    nh = round(w / ratio)
    y0 = (h - nh) // 2
    return 0, y0, w, y0 + nh


def _display_crop_box(t: Optional[str], w: int, h: int) -> Optional[Tuple[int, int, int, int]]:
    """该类型在角色卡里的实际显示区 (源图坐标); 无则 None 走原图。"""
    if t == "card":
        return _panel_visible_box(w, h)
    if t == "bg":
        return _cover_box(w, h, _BG_DISPLAY_RATIO)
    return None


def thumb_path_for(target: Path, max_size: int) -> Path:
    """缩略图缓存路径, 基于源图绝对路径 hash 防冲突 (路径已隐含类型, 无需再编码)。"""
    abs_str = str(target.resolve())
    digest = hashlib.md5(abs_str.encode()).hexdigest()[:12]
    return PANEL_EDIT_THUMBS / f"{digest}_{max_size}_v{_THUMB_VERSION}.webp"


def get_or_make_thumb(target: Path, max_size: int = 360, t: Optional[str] = None) -> Optional[Path]:
    """生成 (或复用) 缩略图, 返回 cache 文件路径。失败返回 None。

    t 为类型 (card/bg/...) 时, 缩略图先裁到角色卡实际显示区再缩放。
    """
    if not target.is_file():
        return None
    cache = thumb_path_for(target, max_size)
    try:
        if cache.exists() and cache.stat().st_mtime >= target.stat().st_mtime:
            return cache
    except OSError:
        pass

    try:
        with Image.open(target) as im:
            box = _display_crop_box(t, im.width, im.height)
            if box:
                im = im.crop(box)
            im = im.convert("RGB") if im.mode in ("RGBA", "LA", "P") else im
            im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            cache.parent.mkdir(parents=True, exist_ok=True)
            im.save(cache, "WEBP", quality=82, method=4)
        return cache
    except Exception as e:
        logger.warning(f"[鸣潮·面板编辑] 生成缩略图失败 {target}: {e}")
        return None


def new_tmp_token() -> str:
    return f"{int(time.time() * 1000):x}_{hash_id_for(str(time.time_ns()))}"


def write_tmp_image(token: str, suffix: str, data: bytes) -> Path:
    """写入临时上传图片。后续裁剪/确认会基于此 token。"""
    suffix = (suffix or ".jpg").lower()
    if suffix not in IMAGE_EXTS:
        suffix = ".jpg"
    target = PANEL_EDIT_TMP / f"{token}{suffix}"
    target.write_bytes(data)
    return target


def find_tmp_files(token: str) -> Tuple[Optional[Path], Optional[Path]]:
    """返回 (current_path, original_path) — 当前 (可能已裁剪的) 与原始备份。"""
    if not is_safe_token(token):
        return None, None
    current: Optional[Path] = None
    original: Optional[Path] = None
    for p in PANEL_EDIT_TMP.iterdir():
        if not p.is_file():
            continue
        if p.stem == token:
            current = p
        elif p.stem == f"{token}.orig":
            original = p
    return current, original


def cleanup_tmp(token: str) -> None:
    if not is_safe_token(token):
        return
    for p in PANEL_EDIT_TMP.iterdir():
        if p.is_file() and (p.stem == token or p.stem == f"{token}.orig"):
            try:
                p.unlink()
            except OSError:
                pass


def gc_tmp(max_age_seconds: int = 6 * 3600) -> None:
    """清理超过 max_age 的临时文件 (默认 6 小时)。"""
    now = time.time()
    for p in PANEL_EDIT_TMP.iterdir():
        if not p.is_file():
            continue
        try:
            if now - p.stat().st_mtime > max_age_seconds:
                p.unlink()
        except OSError:
            pass


def relocate_to_target(t: str, char_id: str, src: Path, suffix_hint: Optional[str] = None) -> Path:
    """把 tmp 文件挪到 (t, char_id) 目录, 返回最终路径。"""
    target_dir = safe_char_dir(t, char_id)
    if target_dir is None:
        raise ValueError(f"unsafe target ({t!r}, {char_id!r})")
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = (suffix_hint or src.suffix or ".jpg").lower()
    if suffix not in IMAGE_EXTS:
        suffix = ".jpg"
    base_ts = int(time.time() * 1000)
    counter = 0
    while True:
        name = f"{char_id}_{base_ts + counter}{suffix}"
        dst = target_dir / name
        if not dst.exists():
            break
        counter += 1
    shutil.move(str(src), str(dst))
    return dst
