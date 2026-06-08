"""排名徽章绘制: 前3名使用PNG图标, 其余使用色块"""

from pathlib import Path

from PIL import Image, ImageDraw

from ..utils.image import get_bot_bg
from ..utils.fonts.waves_fonts import waves_font_18, waves_font_34

TEXT_PATH = Path(__file__).parent / "texture2d"

_BADGE_NAMES = {
    1: "rank_first.png",
    2: "rank_second.png",
    3: "rank_third.png",
}

_BADGE_CACHE: dict = {}


def _load_badge(rank: int):
    if rank not in _BADGE_NAMES:
        return None
    if rank in _BADGE_CACHE:
        return _BADGE_CACHE[rank].copy()

    path = TEXT_PATH / _BADGE_NAMES[rank]
    if not path.exists():
        return None

    badge = Image.open(path).convert("RGBA")
    # 100x100 PNG, 实际内容在中心 45x45, 裁剪后缩放到 50x50
    cx, cy = badge.width // 2, badge.height // 2
    badge = badge.crop((cx - 22, cy - 22, cx + 23, cy + 23))
    badge = badge.resize((55, 55), Image.Resampling.LANCZOS)
    _BADGE_CACHE[rank] = badge
    return badge.copy()


def draw_rank_badge(role_bg: Image.Image, rank_id: int):
    """绘制排名徽章: 前3名用PNG图标, 其余用色块+数字"""
    # Top 3: PNG badge
    if rank_id <= 3:
        badge = _load_badge(rank_id)
        if badge:
            role_bg.alpha_composite(badge, (37, 27))
            return

    # Others: colored box
    rank_color = (54, 54, 54)

    if rank_id > 1000:
        size, draw_pos, dest, text = (100, 50), (50, 24), (10, 30), "999+"
    elif rank_id > 999:
        size, draw_pos, dest, text = (100, 50), (50, 24), (10, 30), str(rank_id)
    elif rank_id > 99:
        size, draw_pos, dest, text = (75, 50), (37, 24), (25, 30), str(rank_id)
    else:
        size, draw_pos, dest, text = (50, 50), (24, 24), (40, 30), str(rank_id)

    info_rank = Image.new("RGBA", size, color=(255, 255, 255, 0))
    rank_draw = ImageDraw.Draw(info_rank)
    rank_draw.rounded_rectangle(
        [0, 0, size[0], size[1]],
        radius=8,
        fill=rank_color + (int(0.9 * 255),),
    )
    rank_draw.text(draw_pos, text, "white", waves_font_34, "mm")
    role_bg.alpha_composite(info_rank, dest)


def draw_bot_name_badge(
    target: Image.Image, background: str, bot_name: str, dest: tuple
) -> None:
    """bot 主人名字徽章 (各排行卡统一调用)。
    背景图不裁剪透明边, 整图按原比例放大 (内容区仍≈200×30, 透明边外扩约4px) 兼容异形边缘;
    dest 为徽章左上角在 target 上的坐标。"""
    info_block = Image.new("RGBA", (208, 39), color=(255, 255, 255, 0))
    bg_img = get_bot_bg(background)
    if bg_img is not None:
        info_block.alpha_composite(bg_img.resize((208, 39)))
    else:
        ImageDraw.Draw(info_block).rounded_rectangle(
            [4, 5, 204, 35], radius=6, fill=(54, 54, 54, int(0.6 * 255))
        )
    ImageDraw.Draw(info_block).text((104, 20), bot_name, "white", waves_font_18, "mm")
    target.alpha_composite(info_block, dest)
