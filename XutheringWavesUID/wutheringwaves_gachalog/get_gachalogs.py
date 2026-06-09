import copy
import json
import base64
import asyncio
from collections import Counter
from typing import Dict, List, Tuple, Union, Optional
from pathlib import Path
from datetime import datetime

import msgspec
import aiofiles

from gsuid_core.logger import logger
from gsuid_core.models import Event

from .model import WWUIDGacha
from ..version import XutheringWavesUID_version
from ..utils.api.model import GachaLog
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from .model_for_waves_plugin import WavesPluginGacha
from ..utils.resource.RESOURCE_PATH import GACHA_BACKUP_PATH, PLAYER_PATH

GACHA_BACKUP_LIMIT = 10

gacha_type_meta_data = {
    "角色精准调谐": "1",
    "武器精准调谐": "2",
    "角色调谐（常驻池）": "3",
    "武器调谐（常驻池）": "4",
    "新手调谐": "5",
    "新手自选唤取": "6",
    "新手自选唤取（感恩定向唤取）": "7",
    "角色新旅唤取": "8",
    "武器新旅唤取": "9",
    "角色联动唤取": "10",
    "武器联动唤取": "11",
}

gacha_type_meta_data_reverse = {v: k for k, v in gacha_type_meta_data.items()}

gachalogs_history_meta = {
    "角色精准调谐": [],
    "武器精准调谐": [],
    "角色调谐（常驻池）": [],
    "武器调谐（常驻池）": [],
    "新手调谐": [],
    "新手自选唤取": [],
    "新手自选唤取（感恩定向唤取）": [],
    "角色新旅唤取": [],
    "武器新旅唤取": [],
    "角色联动唤取": [],
    "武器联动唤取": [],
}

ERROR_MSG_INVALID_LINK = "当前抽卡链接已经失效，请重新导入抽卡链接"


# 找到两个数组中最长公共子串的下标（忽略resourceType字段差异）
def find_longest_common_subarray_indices(
    a: List[GachaLog], b: List[GachaLog]
) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    length = 0
    a_end = b_end = 0

    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            # 使用 match_key() 比较，忽略 resourceType 差异
            if a[i].match_key() == b[j].match_key():
                dp[i][j] = dp[i + 1][j + 1] + 1
                if dp[i][j] > length:
                    length = dp[i][j]
                    a_end = i + length - 1
                    b_end = j + length - 1
            else:
                dp[i][j] = 0

    if length == 0:
        return None

    return (a_end - length + 1, a_end), (b_end - length + 1, b_end)


# 根据最长公共子串递归合并两个GachaLog列表，按time排序
def merge_gacha_logs_by_common_subarray(a: List[GachaLog], b: List[GachaLog]) -> List[GachaLog]:
    common_indices = find_longest_common_subarray_indices(a, b)
    if not common_indices:
        # 无公共子串：保留单侧内部的重复抽数，只合并两侧之间的重叠记录。
        target_counts = Counter(log.match_key() for log in a) | Counter(
            log.match_key() for log in b
        )
        used_counts = Counter()
        merged = []
        for log in a + b:
            key = log.match_key()
            if used_counts[key] >= target_counts[key]:
                continue
            used_counts[key] += 1
            merged.append(log)
        return sorted(
            merged,
            key=lambda log: datetime.strptime(log.time, "%Y-%m-%d %H:%M:%S"),
            reverse=True,
        )

    (a_start, a_end), (b_start, b_end) = common_indices

    prefix = merge_gacha_logs_by_common_subarray(a[:a_start], b[:b_start])
    common_subarray = a[a_start : a_end + 1]
    suffix = merge_gacha_logs_by_common_subarray(a[a_end + 1 :], b[b_end + 1 :])

    return prefix + common_subarray + suffix


async def get_new_gachalog(
    uid: str, record_id: str, full_data: Dict[str, List[GachaLog]], is_force: bool
) -> tuple[Union[str, None], Dict[str, List[GachaLog]], Dict[str, int], Dict[str, List[GachaLog]]]:
    new = {}
    new_count = {}
    link_source_data: Dict[str, List[GachaLog]] = {}
    for gacha_name, card_pool_type in gacha_type_meta_data.items():
        res = await waves_api.get_gacha_log(card_pool_type, record_id, uid)
        if not res.success or not res.data:
            # 抽卡记录获取失败
            if res.code == -1:  # type: ignore
                return ERROR_MSG_INVALID_LINK, None, None, {}  # type: ignore

        if res.data and isinstance(res.data, list):
            temp = res.data
        else:
            temp = []

        gacha_log = [GachaLog.model_validate(log) for log in temp]  # type: ignore
        for log in gacha_log:
            if log.cardPoolType != card_pool_type:
                log.cardPoolType = card_pool_type
        link_source_data[gacha_name] = list(gacha_log)
        common_indices = find_longest_common_subarray_indices(full_data[gacha_name], gacha_log)
        if not common_indices:
            _add = gacha_log
        else:
            (_, _), (b_start, b_end) = common_indices
            _add = gacha_log[:b_start]
        new[gacha_name] = _add + copy.deepcopy(full_data[gacha_name])
        new_count[gacha_name] = len(_add)
        await asyncio.sleep(1)

    return None, new, new_count, link_source_data


async def get_new_gachalog_for_file(
    full_data: Dict[str, List[GachaLog]],
    import_data: Dict[str, List[GachaLog]],
) -> tuple[Union[str, None], Dict[str, List[GachaLog]], Dict[str, int]]:
    new = {}
    new_count = {}

    if str(full_data) == str(import_data):
        for gacha_name, logs in full_data.items():
            new[gacha_name] = list(logs)
            new_count[gacha_name] = 0
        return None, new, new_count

    for cardPoolType, item in import_data.items():
        item: List[GachaLog]
        if cardPoolType not in gacha_type_meta_data:
            continue
        gacha_name = cardPoolType
        gacha_log = [GachaLog(**log.model_dump()) for log in item]
        new_gacha_log = merge_gacha_logs_by_common_subarray(full_data[gacha_name], gacha_log)
        new[gacha_name] = new_gacha_log
        new_count[gacha_name] = len(new_gacha_log)
    return None, new, new_count


def count_new_gachalogs(
    full_data: Dict[str, List[GachaLog]],
    import_data: Dict[str, List[GachaLog]],
) -> Dict[str, int]:
    new_count = {}
    for gacha_name in gacha_type_meta_data:
        full_logs = Counter(log.match_key() for log in full_data.get(gacha_name, []))
        import_logs = Counter(log.match_key() for log in import_data.get(gacha_name, []))
        new_count[gacha_name] = sum((import_logs - full_logs).values())
    return new_count


def prune_gacha_backups(uid: str, type: str, limit: int = GACHA_BACKUP_LIMIT):
    backup_dir = GACHA_BACKUP_PATH / str(uid)
    if not backup_dir.exists():
        return
    files = sorted(
        backup_dir.glob(f"{type}_gacha_logs_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[limit:]:
        try:
            old.unlink()
        except Exception as e:
            logger.warning(f"[鸣潮·抽卡备份] 清理旧备份失败 {old}: {e}")


async def backup_gachalogs(uid: str, gachalogs_history: Dict, type: str):
    backup_dir = GACHA_BACKUP_PATH / str(uid)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{type}_gacha_logs_{datetime.now().strftime('%Y-%m-%d.%H%M%S')}.json"
    async with aiofiles.open(backup_path, "w", encoding="UTF-8") as file:
        await file.write(json.dumps(gachalogs_history, ensure_ascii=False))
    prune_gacha_backups(uid, type)


async def save_link_source_gachalogs(uid: str, record_id: str, data: Dict[str, List[GachaLog]]):
    """保存通过链接获取的抽卡原始数据"""
    path = PLAYER_PATH / str(uid)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    content = {
        "uid": uid,
        "record_id": record_id,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": {gacha_name: [log.model_dump() for log in logs] for gacha_name, logs in data.items()},
    }

    async with aiofiles.open(path / "link_gacha_logs.json", "w", encoding="UTF-8") as file:
        await file.write(json.dumps(content, ensure_ascii=False, indent=2))


async def save_gachalogs(
    ev: Event,
    uid: str,
    record_id: str,
    is_force: bool = False,
    import_data: Optional[Dict[str, List[GachaLog]]] = None,
    force_overwrite: bool = False,
) -> str:
    path = PLAYER_PATH / str(uid)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    # 抽卡记录json路径
    gachalogs_path = path / "gacha_logs.json"

    temp_gachalogs_history = {}
    if gachalogs_path.exists():
        with Path.open(gachalogs_path, encoding="UTF-8") as f:
            gachalogs_history: Dict = json.load(f)

        # import 时备份
        if not record_id:
            await backup_gachalogs(uid, gachalogs_history, type="import")

        # update 时备份
        temp_gachalogs_history = copy.deepcopy(gachalogs_history)

        gachalogs_history = gachalogs_history["data"]
    else:
        gachalogs_history = copy.deepcopy(gachalogs_history_meta)

    temp = copy.deepcopy(gachalogs_history_meta)
    temp.update(gachalogs_history)
    gachalogs_history = temp

    is_need_backup = False
    for gacha_name, card_pool_type in gacha_type_meta_data.items():
        for log in range(len(gachalogs_history[gacha_name]) - 1, -1, -1):
            pool_type = gachalogs_history[gacha_name][log]["cardPoolType"]
            if pool_type == card_pool_type:
                continue
            if card_pool_type == "武器精准调谐" and pool_type == "角色精准调谐-2":
                del gachalogs_history[gacha_name][log]
            elif card_pool_type == "角色调谐（常驻池）" and pool_type == "武器精准调谐":
                del gachalogs_history[gacha_name][log]
            elif card_pool_type == "武器调谐（常驻池）" and pool_type == "全频调谐":
                del gachalogs_history[gacha_name][log]
            else:
                gachalogs_history[gacha_name][log]["cardPoolType"] = card_pool_type

            is_need_backup = True

    if is_need_backup:
        await backup_gachalogs(uid, temp_gachalogs_history, type="update")

    for gacha_name in gacha_type_meta_data.keys():
        gachalogs_history[gacha_name] = [GachaLog(**log) for log in gachalogs_history[gacha_name]]

    link_source_data: Dict[str, List[GachaLog]] = {}
    if record_id:
        code, gachalogs_new, gachalogs_count_add, link_source_data = await get_new_gachalog(
            uid, record_id, gachalogs_history, is_force
        )
    elif not force_overwrite:
        code, gachalogs_new, gachalogs_count_add = await get_new_gachalog_for_file(
            gachalogs_history,
            import_data,  # type: ignore
        )
    else:
        code = None
        gachalogs_new = import_data
        gachalogs_count_add = count_new_gachalogs(gachalogs_history, import_data)  # type: ignore

    if isinstance(code, str) or not gachalogs_new:
        return code or ERROR_MSG_INVALID_LINK

    if record_id and link_source_data:
        await save_link_source_gachalogs(uid, record_id, link_source_data)

    # 获取当前时间
    current_time = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

    # 检查并修正时间降序
    for gacha_name in gacha_type_meta_data.keys():
        logs = gachalogs_new.get(gacha_name, [])
        if len(logs) > 1:
            # 从末尾倒着检查时间顺序
            for i in range(len(logs) - 1, 0, -1):
                time_current = datetime.strptime(logs[i].time, "%Y-%m-%d %H:%M:%S")
                time_prev = datetime.strptime(logs[i - 1].time, "%Y-%m-%d %H:%M:%S")

                # 如果第 i-1 个的时间小于第 i 个，说明顺序不对，舍弃 i-1 及之前的所有记录
                if time_prev < time_current:
                    logger.warning(f"[鸣潮·抽卡导入] 卡池[{gacha_name}] 发现时间顺序异常，舍弃索引 {i - 1} 及之前的 {i} 条记录")
                    gachalogs_new[gacha_name] = logs[i:]
                    break

    # 初始化最后保存的数据
    result = {"uid": uid, "data_time": current_time}

    # 保存数量
    for gacha_name in gacha_type_meta_data.keys():
        result[gacha_name] = len(gachalogs_new.get(gacha_name, []))  # type: ignore

    result["data"] = {  # type: ignore
        gacha_name: [log.model_dump() for log in gachalogs_new.get(gacha_name, [])]
        for gacha_name in gacha_type_meta_data.keys()
    }

    vo = msgspec.to_builtins(result)
    async with aiofiles.open(gachalogs_path, "w", encoding="UTF-8") as file:
        await file.write(json.dumps(vo, ensure_ascii=False))

    # 失效 stats 缓存：下次抽卡记录/抽卡排行查询时 lazy 重建
    (path / "gachaStats.json").unlink(missing_ok=True)

    # 计算数据
    all_add = sum(gachalogs_count_add.values())

    # 回复文字
    user_pref = await get_hide_uid_pref(uid, ev.user_id, ev.bot_id)
    im = []
    if all_add == 0:
        im.append(f"🌱UID{hide_uid(uid, user_pref)}没有新增唤取数据!")
    else:
        im.append(f"🌱UID{hide_uid(uid, user_pref)}数据更新成功！")
        for k, v in gachalogs_count_add.items():
            if v > 0:
                im.append(f"[{k}]新增{v}个数据！")
        from .web_view import _is_feature_enabled as _gw_enabled
        from ..wutheringwaves_config import PREFIX as _gw_prefix
        if _gw_enabled():
            im.append(f"可发送 {_gw_prefix}抽卡页面 查看更具体记录")
    im = "\n".join(im)
    return im




async def import_gachalogs(ev: Event, history_url: str, type: str, uid: str, force_overwrite=False) -> str:
    history_data: Dict = {}
    if type == "json":
        history_data = json.loads(history_url)
    else:
        data_bytes = base64.b64decode(history_url)
        try:
            history_data = json.loads(data_bytes.decode())
        except UnicodeDecodeError:
            history_data = json.loads(data_bytes.decode("gbk"))
        except json.decoder.JSONDecodeError:
            return "请传入正确的JSON格式文件!"

    def turn_wwuid_gacha(data: Dict) -> Optional[WWUIDGacha]:
        if "info" in data and "export_app" in data["info"]:
            if "Waves-Plugin" == data["info"]["export_app"]:
                return WavesPluginGacha.model_validate(data).turn_wwuid_gacha()
            elif "XutheringWavesUID" == data["info"]["export_app"] or "WutheringWavesUID" == data["info"]["export_app"]:
                return WWUIDGacha.model_validate(data)
        return None

    wwuid_gacha = turn_wwuid_gacha(history_data)
    if not wwuid_gacha:
        err_res = [
            "你当前导入的抽卡记录文件不支持, 目前支持的文件类型有:",
            "1.WutheringWavesUID",
            "2.XutheringWavesUID",
            "3.Waves-Plugin",
        ]
        return "\n".join(err_res)

    if wwuid_gacha.info.uid != uid:
        return "你当前导入的抽卡记录文件的UID与当前UID不匹配!"

    import_data = copy.deepcopy(gachalogs_history_meta)
    for item in wwuid_gacha.list:
        gacha_name = item.cardPoolType
        if gacha_name in gacha_type_meta_data:
            # 此时cardPoolType是名字 -> 如角色精准调谐
            item.cardPoolType = gacha_type_meta_data[gacha_name]
        else:
            # 此时cardPoolType是类型 -> 如 "1"
            gacha_name = gacha_type_meta_data_reverse.get(item.cardPoolType)
            if not gacha_name:
                continue
        import_data[gacha_name].append(GachaLog(**item.model_dump()))

    res = await save_gachalogs(ev, uid, "", import_data=import_data, force_overwrite=force_overwrite)
    return res


async def export_gachalogs(uid: str) -> dict:
    path = PLAYER_PATH / uid
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    # 获取当前时间
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")

    # 抽卡记录json路径
    gachalogs_path = path / "gacha_logs.json"
    if gachalogs_path.exists():
        async with aiofiles.open(gachalogs_path, "r", encoding="UTF-8") as f:
            raw_data = json.loads(await f.read())

        result = {
            "info": {
                "export_time": current_time,
                "export_app": "XutheringWavesUID",
                "export_app_version": XutheringWavesUID_version,
                "export_timestamp": round(now.timestamp()),
                "version": "v2.0",
                "uid": uid,
            },
            "list": [],
        }
        gachalogs_history = raw_data["data"]
        for name, gachalogs in gachalogs_history.items():
            result["list"].extend(gachalogs)

        async with aiofiles.open(path / f"export_{uid}.json", "w", encoding="UTF-8") as file:
            await file.write(json.dumps(result, ensure_ascii=False, indent=4))

        logger.success("[鸣潮·导出抽卡记录] 导出成功!")
        im = {
            "retcode": "ok",
            "data": "导出成功!",
            "name": f"export_{uid}.json",
            "url": str((path / f"export_{uid}.json").absolute()),
        }
    else:
        logger.error("[鸣潮·导出抽卡记录] 没有找到抽卡记录!")
        im = {
            "retcode": "error",
            "data": "你还没有抽卡记录可以导出!",
            "name": "",
            "url": "",
        }

    return im
