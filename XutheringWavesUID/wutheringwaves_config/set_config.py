from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.constants import WAVES_GAME_ID
from ..utils.name_convert import is_valid_char_name, alias_to_char_name
from ..utils.database.models import WavesUser
from ..utils.util import get_hide_uid_pref, hide_uid

WAVES_USER_MAP = {
    "体力背景": "stamina_bg",
    "隐藏UID": "hide_uid_self",
}


def _is_valid_stamina_bg_hash(hash_id: str) -> bool:
    # 此模块在 wutheringwaves_config 包初始化阶段被加载, 而 card_hash_index 反向需要 PREFIX,
    # 顶层 import 会触发 partial init 循环; 所以下放到函数内, 命令真正调用时才解析。
    from ..wutheringwaves_charinfo.card_hash_index import is_valid_hash
    return is_valid_hash(hash_id, types=("bg", "stamina"))


async def set_waves_user_value(ev: Event, func: str, uid: str, value: str):
    if func in WAVES_USER_MAP:
        status = WAVES_USER_MAP[func]
    else:
        return "该配置项不存在!"
    logger.info("[鸣潮·设置{}] uid:{} value: {}".format(func, uid, value))
    if (
        await WavesUser.update_data_by_data(
            select_data={
                "user_id": ev.user_id,
                "bot_id": ev.bot_id,
                "uid": uid,
                "game_id": WAVES_GAME_ID,
            },
            update_data={f"{status}_value": value},
        )
        == 0
    ):
        if func == "隐藏UID":
            # 调度层只会传 on/off; 用 value 做即时回显, 无需再读 DB
            masked_uid = hide_uid(uid, user_pref=value)
            action = "已开启" if value == "on" else "已关闭"
            return f"{action}隐藏UID!\n特征码[{masked_uid}]"
        masked_uid = hide_uid(
            uid,
            user_pref=await get_hide_uid_pref(uid, ev.user_id, ev.bot_id),
        )
        if func == "体力背景":
            if not value:
                return f"已重置体力背景为默认!\n特征码[{masked_uid}]"
            pure_value = value.replace("官方", "").replace("立绘", "").replace("背景", "").replace("图", "")
            if not pure_value.strip():
                # 只给修饰词(背景/立绘/官方)不带角色名/ID → 走随机池
                if any(k in value for k in ("背景", "立绘", "官方")):
                    return f"设置成功!\n特征码[{masked_uid}]\n当前{func}:{value}\n(未指定角色, 将按类型随机选图)"
                return f"未找到对应体力背景!\n请检查输入的角色名称或图片ID是否正确!"
            if is_valid_char_name(pure_value):
                value = alias_to_char_name(pure_value) + ("官方" if "官方" in value else "") + ("立绘" if "立绘" in value else "") + ("背景" if "背景" in value else "")
                return f"设置成功!\n特征码[{masked_uid}]\n当前{func}:{value}\n例:[椿](官方)(立绘/背景)\n或直接设为固定图片ID"
            elif _is_valid_stamina_bg_hash(pure_value):
                return f"设置成功!\n特征码[{masked_uid}]\n当前{func}:{value}"
            else:
                return f"未找到对应体力背景!\n请检查输入的角色名称或图片ID是否正确!"
        else:
            return f"设置成功!\n特征码[{masked_uid}]\n当前{func}:{value}"
    else:
        return "设置失败!\n请检查参数是否正确!"
