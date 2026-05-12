import re
import copy
import json
import math
import time
import asyncio
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta

import httpx
import aiofiles
from PIL import Image, ImageDraw, ImageFont

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.util import get_version, hide_uid
from ..utils.image import (
    RED,
    GREY,
    AMBER,
    WAVES_VOID,
    WAVES_MOLTEN,
    WAVES_SIERRA,
    WAVES_MOONLIT,
    WAVES_FREEZING,
    WAVES_LINGERING,
    get_ICON,
    add_footer,
    get_waves_bg,
    get_square_avatar,
    pic_download_from_url,
    parse_bot_color_config,
)
from .rank_badge import draw_rank_badge
from .rank_avatar import get_avatar
from ..utils.resource.RESOURCE_PATH import MATRIX_PATH
from ..utils.api.model import MatrixDetail
from ..utils.api.wwapi import (
    GET_MATRIX_RANK_URL,
    MatrixRank,
    MatrixRankRes,
    MatrixRankItem,
)
from ..utils.ascension.char import get_char_model
from ..utils.database.models import WavesBind, WavesUser
from ..utils.resource.constant import SPECIAL_CHAR_INT_ALL, NORMAL_LIST_IDS, randomize_special_char_id
from ..wutheringwaves_config import PREFIX, WutheringWavesConfig
from ..utils.fonts.waves_fonts import (
    waves_font_12,
    waves_font_18,
    waves_font_20,
    waves_font_34,
    waves_font_44,
    waves_font_58,
)
from ..wutheringwaves_abyss.period import (
    MATRIX_BASE_TIMESTAMP,
    get_matrix_period_number,
    is_matrix_record_expired,
)

TEXT_PATH = Path(__file__).parent / "texture2d"

CHINA_TZ = timezone(timedelta(hours=8))

BOT_COLOR = [
    WAVES_MOLTEN,
    AMBER,
    WAVES_VOID,
    WAVES_SIERRA,
    WAVES_FREEZING,
    WAVES_LINGERING,
    WAVES_MOONLIT,
]



from ._colors import (
    CRYSTAL_SENTINEL,
    draw_crystal_text,
    get_matrix_local_rank_color as get_local_score_color,
    get_matrix_total_rank_color as get_score_color,
)


async def get_rank(item: MatrixRankItem) -> Optional[MatrixRankRes]:
    WavesToken = WutheringWavesConfig.get_config("WavesToken").data

    if not WavesToken:
        return

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                GET_MATRIX_RANK_URL,
                json=item.model_dump(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WavesToken}",
                },
                timeout=httpx.Timeout(10),
            )
            if res.status_code == 200:
                return MatrixRankRes.model_validate(res.json())
            else:
                logger.warning(f"获取矩阵排行失败: {res.status_code} - {res.text}")
        except Exception as e:
            logger.exception(f"获取矩阵排行失败: {e}")


async def draw_all_matrix_rank_card(bot: Bot, ev: Event):
    waves_id = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
    match = re.search(r"(\d+)", ev.raw_text)
    if match:
        pages = int(match.group(1))
    else:
        pages = 1
    pages = max(pages, 1)
    pages = min(pages, 5)
    page_num = 20
    item = MatrixRankItem(
        page=pages,
        page_num=page_num,
        waves_id=waves_id or "",
        version=get_version(dynamic=True, waves_id=waves_id or "", pages=pages),
    )

    rankInfoList = await get_rank(item)
    if not rankInfoList:
        return "获取矩阵排行失败"

    if rankInfoList.message and not rankInfoList.data:
        return rankInfoList.message

    if not rankInfoList.data:
        return "获取矩阵排行失败"

    # 设置图像尺寸
    width = 1300
    item_spacing = 120
    header_height = 510
    footer_height = 50
    char_list_len = len(rankInfoList.data.rank_list)

    total_height = header_height + item_spacing * char_list_len + footer_height

    card_img = get_waves_bg(width, total_height, "bg9")

    # title — 使用 matrix.png
    title_bg = Image.open(TEXT_PATH / "matrix.png").convert("RGBA")
    title_scale = width / title_bg.width
    title_bg = title_bg.resize((width, int(title_bg.height * title_scale)))
    if title_bg.height > 500:
        title_bg = title_bg.crop((0, 0, width, 500))
    else:
        temp = Image.new("RGBA", (width, 500), (0, 0, 0, 0))
        temp.paste(title_bg, (0, 500 - title_bg.height))
        title_bg = temp

    # icon
    icon = get_ICON()
    icon = icon.resize((128, 128))
    title_bg.paste(icon, (60, 240), icon)

    # title text
    title_text = "#矩阵总排行"
    title_bg_draw = ImageDraw.Draw(title_bg)
    title_bg_draw.text((220, 290), title_text, "white", waves_font_58, "lm")

    period_label = f"第{get_matrix_period_number()}期"
    date_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    period_pos = (225, 360)
    title_bg_draw.text(period_pos, period_label, GREY, waves_font_20, "lm")
    try:
        period_width = title_bg_draw.textlength(period_label, font=waves_font_20)
    except Exception:
        period_width = waves_font_20.getsize(period_label)[0]
    title_bg_draw.text(
        (period_pos[0] + period_width + 16, period_pos[1]),
        date_text,
        GREY,
        waves_font_20,
        "lm",
    )

    # 遮罩
    char_mask = Image.open(TEXT_PATH / "char_mask.png").convert("RGBA")
    char_mask = char_mask.resize((width, char_mask.height * width // char_mask.width))
    char_mask = char_mask.crop((0, char_mask.height - 500, width, char_mask.height))
    char_mask_temp = Image.new("RGBA", char_mask.size, (0, 0, 0, 0))
    char_mask_temp.paste(title_bg, (0, 0), char_mask)

    card_img.paste(char_mask_temp, (0, 0), char_mask_temp)

    rank_list = rankInfoList.data.rank_list
    tasks = [get_avatar(rank.user_id, getattr(rank, "sender_avatar", "")) for rank in rank_list]
    results = await asyncio.gather(*tasks)

    bot_color_map = parse_bot_color_config(
        WutheringWavesConfig.get_config("BotColorMap").data
    )
    bot_color = copy.deepcopy(BOT_COLOR)

    for rank_temp_index, temp in enumerate(zip(rank_list, results)):
        rank_temp: MatrixRank = temp[0]
        role_avatar: Image.Image = temp[1]
        role_bg = Image.open(TEXT_PATH / "bar1.png")
        role_bg.paste(role_avatar, (100, 0), role_avatar)
        role_bg_draw = ImageDraw.Draw(role_bg)

        # 排名
        rank_id = rank_temp.rank
        draw_rank_badge(role_bg, rank_id)

        # 名字
        role_bg_draw.text((210, 75), f"{rank_temp.kuro_name}", "white", waves_font_20, "lm")

        # 特征码 — 移到名字上方，不带 "特征码:" 前缀
        uid_color = "white"
        if rank_temp.waves_id == item.waves_id:
            uid_color = RED
        role_bg_draw.text((210, 40), f"{hide_uid(rank_temp.waves_id)}", uid_color, waves_font_20, "lm")

        # 原特征码位置 → 显示上场队伍数量（未登录时为0，不显示）
        team_count = rank_temp.team_count if rank_temp.team_count else len(rank_temp.teams)
        if team_count:
            role_bg_draw.text((350, 40), f"上场队伍数量: {team_count}", GREY, waves_font_20, "lm")

        # bot主人名字
        botName = rank_temp.alias_name if rank_temp.alias_name else ""
        if botName:
            color = (54, 54, 54)
            if botName in bot_color_map:
                color = bot_color_map[botName]
            elif bot_color:
                color = bot_color.pop(0)
                bot_color_map[botName] = color

            info_block = Image.new("RGBA", (200, 30), color=(255, 255, 255, 0))
            info_block_draw = ImageDraw.Draw(info_block)
            info_block_draw.rounded_rectangle([0, 0, 200, 30], radius=6, fill=color + (int(0.6 * 255),))
            info_block_draw.text((100, 15), f"bot: {botName}", "white", waves_font_18, "mm")
            role_bg.alpha_composite(info_block, (330, 66))

        # 总分数 — 左移10px (矩阵分数比海墟多一位)
        score_color = get_score_color(rank_temp.score)
        if score_color == CRYSTAL_SENTINEL:
            draw_crystal_text(role_bg, f"{rank_temp.score}", 1130, 55, waves_font_44, "mm")
        else:
            role_bg_draw.text(
                (1130, 55),
                f"{rank_temp.score}",
                score_color,
                waves_font_44,
                "mm",
            )

        # 队伍角色 — 整体左移20px
        team_base_x = 550
        team_spacing = 250

        # 按分数排序取最高和次高
        sorted_teams = sorted(rank_temp.teams, key=lambda t: t.score, reverse=True)

        for team_index, matrix_team in enumerate(sorted_teams[:2]):
            # 角色头像
            for role_index, char_detail in enumerate(matrix_team.char_detail):
                char_id = char_detail.char_id
                char_chain = char_detail.chain

                char_id = randomize_special_char_id(char_id)
                char_model = get_char_model(char_id)
                if char_model is None:
                    continue
                char_avatar = await get_square_avatar(char_id)
                char_avatar = char_avatar.resize((45, 45))

                if char_chain != -1:
                    info_block = Image.new("RGBA", (20, 20), color=(255, 255, 255, 0))
                    info_block_draw = ImageDraw.Draw(info_block)
                    info_block_draw.rectangle([0, 0, 20, 20], fill=(96, 12, 120, int(0.9 * 255)))
                    info_block_draw.text(
                        (8, 8),
                        f"{char_chain}",
                        "white",
                        waves_font_12,
                        "mm",
                    )
                    char_avatar.paste(info_block, (30, 30), info_block)

                role_bg.alpha_composite(char_avatar, (team_base_x + team_index * team_spacing + role_index * 50, 20))

            # 角色头像为空时，尝试用 role_icons URL 下载显示
            if not matrix_team.char_detail and matrix_team.role_icons:
                for role_index, icon_url in enumerate(matrix_team.role_icons):
                    try:
                        role_pic = await pic_download_from_url(MATRIX_PATH, icon_url)
                        role_pic = role_pic.resize((45, 45))
                        circle_mask = Image.new("L", (45, 45), 0)
                        circle_draw = ImageDraw.Draw(circle_mask)
                        circle_draw.ellipse([0, 0, 44, 44], fill=255)
                        role_circle = Image.new("RGBA", (45, 45), (0, 0, 0, 0))
                        role_circle.paste(role_pic, (0, 0), circle_mask)
                        role_bg.alpha_composite(role_circle, (team_base_x + team_index * team_spacing + role_index * 50, 20))
                    except Exception:
                        pass

            # 不足3人时用 "模版\n角色" 文字占位
            actual_count = len(matrix_team.char_detail) or len(matrix_team.role_icons)
            for empty_idx in range(actual_count, 3):
                placeholder = Image.new("RGBA", (45, 45), (60, 60, 60, int(0.5 * 255)))
                ph_draw = ImageDraw.Draw(placeholder)
                ph_draw.rectangle([0, 0, 44, 44], outline=(120, 120, 120, 200), width=1)
                ph_draw.text((22, 16), "模版", GREY, waves_font_12, "mm")
                ph_draw.text((22, 32), "角色", GREY, waves_font_12, "mm")
                role_bg.alpha_composite(placeholder, (team_base_x + team_index * team_spacing + empty_idx * 50, 20))

            # buff icon
            if matrix_team.buff_icon:
                try:
                    buff_bg = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
                    buff_bg_draw = ImageDraw.Draw(buff_bg)
                    buff_bg_draw.rounded_rectangle(
                        [0, 0, 50, 50],
                        radius=5,
                        fill=(0, 0, 0, int(0.8 * 255)),
                    )
                    buff_pic = await pic_download_from_url(MATRIX_PATH, matrix_team.buff_icon)
                    buff_pic = buff_pic.resize((50, 50))
                    buff_bg.paste(buff_pic, (0, 0), buff_pic)
                    # 角色头像最多3个(150px)，buff放在角色后面
                    role_bg.alpha_composite(buff_bg, (team_base_x + team_index * team_spacing + 160, 15))
                except Exception as e:
                    logger.debug(f"绘制矩阵buff图标失败: {e}")

            # 队伍得分标签 — 与上方 角色(3×50) + buff(10+50) 整体居中
            # 整体宽度 = 150 + 10 + 50 = 210，中心偏移 = 105
            block_center_x = team_base_x + team_index * team_spacing + 105
            score_label = "最高单队得分" if team_index == 0 else "次高单队得分"
            role_bg_draw.text(
                (block_center_x, 80),
                f"{score_label}: {matrix_team.score}",
                "white",
                waves_font_18,
                "mm",
            )

        card_img.paste(role_bg, (0, 510 + rank_temp_index * item_spacing), role_bg)

    card_img = add_footer(card_img)
    card_img = await convert_img(card_img)
    return card_img


class MatrixTeamInfo:
    """排行中的队伍摘要"""

    def __init__(self, score: int, role_icons: List[str],
                 buff_icon: str = "", char_ids: Optional[List[int]] = None):
        self.score = score
        self.role_icons = role_icons  # URL 列表
        self.buff_icon = buff_icon  # buff图标 URL
        self.char_ids = char_ids or []  # 匹配到的角色ID (可能为空)


class MatrixRankListInfo:
    """矩阵排行信息"""

    def __init__(self, user_id: str, uid: str,
                 matrix_data: Optional[MatrixDetail] = None,
                 matched_char_ids: Optional[Dict] = None):
        self.user_id = user_id
        self.uid = uid
        self.matrix_data = matrix_data
        self.score = 0
        self.top_teams: List[MatrixTeamInfo] = []

        self.all_char_ids: List[int] = []  # 所有队伍的角色ID (用于计算总金数)

        matched = matched_char_ids or {}

        if matrix_data and matrix_data.modeDetails:
            mode_1 = next((m for m in matrix_data.modeDetails if m.modeId == 1 and m.hasRecord), None)
            if mode_1:
                self.score = mode_1.score
                if mode_1.teams:
                    # 收集所有队伍的 char_ids
                    for idx in range(len(mode_1.teams)):
                        ids = matched.get(f"1_{idx}", [])
                        self.all_char_ids.extend(ids)

                    # 按分数降序取前两队展示
                    indexed_teams = list(enumerate(mode_1.teams))
                    indexed_teams.sort(key=lambda x: x[1].score, reverse=True)
                    for orig_idx, t in indexed_teams[:2]:
                        ids = matched.get(f"1_{orig_idx}", [])
                        self.top_teams.append(
                            MatrixTeamInfo(
                                t.score,
                                t.roleIcons,
                                t.buffs[0].buffIcon if t.buffs else "",
                                ids,
                            )
                        )


async def get_all_matrix_rank_info(
    users: List[WavesBind],
    tokenLimitFlag: bool = False,
    wavesTokenUsersMap: Optional[Dict[Tuple[str, str], str]] = None,
) -> List[MatrixRankListInfo]:
    """从本地获取所有用户的矩阵排行信息"""
    from ..utils.resource.RESOURCE_PATH import PLAYER_PATH

    rankInfoList = []

    for user in users:
        if not user.uid:
            continue

        for uid in user.uid.split("_"):
            if tokenLimitFlag and wavesTokenUsersMap is not None:
                if (user.user_id, uid) not in wavesTokenUsersMap:
                    continue
            try:
                matrix_data_path = Path(PLAYER_PATH / uid / "matrixData.json")
                if not matrix_data_path.exists():
                    continue

                async with aiofiles.open(matrix_data_path, mode="r", encoding="utf-8") as f:
                    matrix_raw = json.loads(await f.read())

                record_time = None
                matrix_data = matrix_raw
                matched_char_ids = None
                if isinstance(matrix_raw, dict) and "matrix_data" in matrix_raw:
                    record_time = matrix_raw.get("record_time", MATRIX_BASE_TIMESTAMP)
                    matrix_data = matrix_raw.get("matrix_data")
                    matched_char_ids = matrix_raw.get("matched_char_ids")

                if not isinstance(matrix_data, dict) or not matrix_data:
                    continue

                if is_matrix_record_expired(record_time):
                    logger.debug(f"用户{uid}矩阵数据已过期，跳过")
                    continue

                if not matrix_data.get("isUnlock", False):
                    continue

                matrix_data = MatrixDetail.model_validate(matrix_data)

                rankInfo = MatrixRankListInfo(
                    user.user_id, uid, matrix_data, matched_char_ids
                )
                if rankInfo.score > 0:
                    rankInfoList.append(rankInfo)
            except Exception as e:
                logger.debug(f"获取用户{uid}本地矩阵数据失败: {e}")
                continue

    return rankInfoList


async def get_matrix_rank_token_condition(ev) -> Tuple[bool, Dict[Tuple[str, str], str]]:
    """检查矩阵排行的权限配置 (与冥海一致)"""
    tokenLimitFlag = False
    wavesTokenUsersMap: Dict[Tuple[str, str], str] = {}

    WavesRankNoLimitGroup = WutheringWavesConfig.get_config("WavesRankNoLimitGroup").data
    if ev.group_id and WavesRankNoLimitGroup and ev.group_id in WavesRankNoLimitGroup:
        return tokenLimitFlag, wavesTokenUsersMap

    WavesRankUseTokenGroup = WutheringWavesConfig.get_config("WavesRankUseTokenGroup").data
    RankUseToken = WutheringWavesConfig.get_config("RankUseToken").data
    if (ev.group_id and WavesRankUseTokenGroup and ev.group_id in WavesRankUseTokenGroup) or RankUseToken:
        wavesTokenUsers = await WavesUser.get_waves_all_user()
        wavesTokenUsersMap = {(w.user_id, w.uid): w.cookie for w in wavesTokenUsers}
        tokenLimitFlag = True

    return tokenLimitFlag, wavesTokenUsersMap


async def get_role_chain_count(uid: str, role_id: int) -> int:
    """从rawData.json获取角色共鸣链数量，特殊角色遍历所有形态"""
    from ..utils.resource.RESOURCE_PATH import PLAYER_PATH
    from ..utils.resource.constant import SPECIAL_CHAR_INT_ALL

    # 漂泊者的所有形态头像可能互相匹配，遍历全部6个ID
    candidates = SPECIAL_CHAR_INT_ALL if role_id in SPECIAL_CHAR_INT_ALL else [role_id]

    try:
        raw_data_path = Path(PLAYER_PATH / str(uid) / "rawData.json")
        if not raw_data_path.exists():
            return -1

        async with aiofiles.open(raw_data_path, mode="r", encoding="utf-8") as f:
            raw_data = json.loads(await f.read())

        if isinstance(raw_data, list):
            for cid in candidates:
                for role_data in raw_data:
                    if role_data.get("role", {}).get("roleId") == cid:
                        chain_list = role_data.get("chainList", [])
                        unlocked_chains = [c for c in chain_list if c.get("unlocked", False)]
                        return len(unlocked_chains)
        return -1
    except Exception as e:
        logger.debug(f"获取角色{role_id}共鸣链失败: {e}")
        return -1


async def draw_matrix_rank_list(bot: Bot, ev: Event):
    """绘制矩阵群排行 (PIL)"""
    start_time = time.time()
    logger.info(f"[draw_matrix_rank_list] start: {start_time}")

    # 检查权限配置
    tokenLimitFlag, wavesTokenUsersMap = await get_matrix_rank_token_condition(ev)

    # 获取群里的所有用户
    users = await WavesBind.get_group_all_uid(ev.group_id)
    if not users:
        msg = []
        msg.append(f"[鸣潮] 群【{ev.group_id}】暂无矩阵排行数据")
        msg.append(f"请使用【{PREFIX}矩阵】后再使用此功能！")
        if tokenLimitFlag:
            msg.append(f"当前排行开启了登录验证，请使用命令【{PREFIX}登录】登录后此功能！")
        msg.append("")
        return "\n".join(msg)

    rankInfoList = await get_all_matrix_rank_info(list(users), tokenLimitFlag, wavesTokenUsersMap)
    if len(rankInfoList) == 0:
        msg = []
        msg.append(f"[鸣潮] 群【{ev.group_id}】暂无矩阵排行数据")
        msg.append(f"请使用【{PREFIX}矩阵】后再使用此功能！")
        if tokenLimitFlag:
            msg.append(f"当前排行开启了登录验证，请使用命令【{PREFIX}登录】登录后此功能！")
        msg.append("")
        return "\n".join(msg)

    # 按分数排序
    rankInfoList.sort(key=lambda i: i.score, reverse=True)

    # 获取自己的排名
    self_uid = None
    rankId = None
    rankInfo = None
    try:
        self_uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
        if self_uid:
            rankId, rankInfo = next(
                (
                    (rankId, rankInfo)
                    for rankId, rankInfo in enumerate(rankInfoList, start=1)
                    if rankInfo.uid == self_uid and ev.user_id == rankInfo.user_id
                ),
                (None, None),
            )
    except Exception:
        pass

    rank_length = 20
    rankInfoList_display = rankInfoList[:rank_length]
    if rankId and rankInfo and rankId > rank_length:
        rankInfoList_display.append(rankInfo)

    # 设置图像尺寸
    width = 1000
    item_spacing = 120
    header_height = 510
    footer_height = 50

    total_height = header_height + item_spacing * len(rankInfoList_display) + footer_height

    card_img = get_waves_bg(width, total_height, "bg9")

    # title — 使用 matrix.png
    title_bg = Image.open(TEXT_PATH / "matrix.png").convert("RGBA")
    # 缩放到 width 宽度，保持比例
    title_scale = width / title_bg.width
    title_bg = title_bg.resize((width, int(title_bg.height * title_scale)))
    # 裁剪到 475 高度
    if title_bg.height > 475:
        title_bg = title_bg.crop((0, 0, width, 475))
    else:
        # 如果不够高，创建一个 475 高度的画布
        temp = Image.new("RGBA", (width, 475), (0, 0, 0, 0))
        temp.paste(title_bg, (0, 475 - title_bg.height))
        title_bg = temp

    # icon
    icon = get_ICON()
    icon = icon.resize((128, 128))
    title_bg.paste(icon, (60, 240), icon)

    # title text
    title_text = "#矩阵群排行"
    title_bg_draw = ImageDraw.Draw(title_bg)
    title_bg_draw.text((220, 290), title_text, "white", waves_font_58, "lm")
    title_bg_draw.text(
        (225, 360),
        f"第{get_matrix_period_number()}期",
        GREY,
        waves_font_20,
        "lm",
    )

    # 遮罩
    char_mask = Image.open(TEXT_PATH / "char_mask.png").convert("RGBA")
    char_mask = char_mask.resize((width, char_mask.height * width // char_mask.width))
    char_mask = char_mask.crop((0, char_mask.height - 475, width, char_mask.height))
    char_mask_temp = Image.new("RGBA", char_mask.size, (0, 0, 0, 0))
    char_mask_temp.paste(title_bg, (0, 0), char_mask)

    card_img.paste(char_mask_temp, (0, 0), char_mask_temp)

    # 获取头像
    tasks = [get_avatar(rank.user_id, getattr(rank, "sender_avatar", "")) for rank in rankInfoList_display]
    results = await asyncio.gather(*tasks)

    # 绘制排行条目
    bar = Image.open(TEXT_PATH / "bar2.png")

    for rank_temp_index, temp in enumerate(zip(rankInfoList_display, results)):
        rankInfo = temp[0]
        role_avatar = temp[1]
        role_bg = bar.copy()
        role_bg.paste(role_avatar, (100, 0), role_avatar)
        role_bg_draw = ImageDraw.Draw(role_bg)

        # 排名
        rank_id = rank_temp_index + 1
        draw_rank_badge(role_bg, rank_id)

        # 计算所有队伍出场限定角色的金数（去重，排除常驻和漂泊者）
        char_gold_total = 0
        seen_ids = set()
        for role_id in rankInfo.all_char_ids:
            if role_id in seen_ids:
                continue
            seen_ids.add(role_id)
            if role_id in SPECIAL_CHAR_INT_ALL or role_id in NORMAL_LIST_IDS:
                continue
            char_model = get_char_model(role_id)
            if char_model and char_model.starLevel == 5:
                chain_count = await get_role_chain_count(rankInfo.uid, role_id)
                char_gold_total += (chain_count + 1) if chain_count >= 0 else 0

        role_bg_draw.text((210, 40), f"限定角色金数: {char_gold_total}", "white", waves_font_18, "lm")

        # 特征码
        uid_color = "white"
        if rankInfo.uid == self_uid:
            uid_color = RED
        role_bg_draw.text((210, 70), f"{rankInfo.uid}", uid_color, waves_font_20, "lm")

        # 总分数 (右侧，左移25px)
        total_color = get_local_score_color(rankInfo.score)
        if total_color == CRYSTAL_SENTINEL:
            draw_crystal_text(role_bg, f"{rankInfo.score}", 875, 55, waves_font_34, "mm")
        else:
            role_bg_draw.text(
                (875, 55),
                f"{rankInfo.score}",
                total_color,
                waves_font_34,
                "mm",
            )

        # 上下两队: 角色头像 + buff + 得分
        for half_index, team_info in enumerate(rankInfo.top_teams):
            base_x = 365 + half_index * 230

            # 角色头像 (从URL下载, 方形) + 共鸣链
            for role_index, icon_url in enumerate(team_info.role_icons):
                try:
                    role_pic = await pic_download_from_url(MATRIX_PATH, icon_url)
                    role_pic = role_pic.resize((45, 45))

                    # 如果有对应的 char_id，绘制共鸣链
                    if role_index < len(team_info.char_ids) and team_info.char_ids[role_index]:
                        char_id = team_info.char_ids[role_index]
                        chain_count = await get_role_chain_count(rankInfo.uid, char_id)
                        if chain_count != -1:
                            info_block = Image.new("RGBA", (20, 20), color=(255, 255, 255, 0))
                            info_block_draw = ImageDraw.Draw(info_block)
                            info_block_draw.rectangle([0, 0, 20, 20], fill=(96, 12, 120, int(0.9 * 255)))
                            info_block_draw.text(
                                (8, 8),
                                f"{chain_count}",
                                "white",
                                waves_font_12,
                                "mm",
                            )
                            role_pic.paste(info_block, (30, 30), info_block)

                    role_bg.alpha_composite(role_pic, (base_x + role_index * 50, 20))
                except Exception as e:
                    logger.debug(f"绘制矩阵角色头像失败: {e}")

            # buff图标 (与slash信物位置一致)
            if team_info.buff_icon:
                try:
                    buff_bg = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
                    buff_bg_draw = ImageDraw.Draw(buff_bg)
                    buff_bg_draw.rounded_rectangle(
                        [0, 0, 50, 50],
                        radius=5,
                        fill=(0, 0, 0, int(0.8 * 255)),
                    )
                    buff_pic = await pic_download_from_url(MATRIX_PATH, team_info.buff_icon)
                    buff_pic = buff_pic.resize((50, 50))
                    buff_bg.paste(buff_pic, (0, 0), buff_pic)
                    role_bg.alpha_composite(buff_bg, (base_x + 150, 15))
                except Exception as e:
                    logger.debug(f"绘制矩阵buff失败: {e}")

            # 队伍分数 (在角色和buff下方)
            team_color = get_local_score_color(team_info.score)
            if team_color == CRYSTAL_SENTINEL:
                draw_crystal_text(role_bg, f"{team_info.score}", base_x + 100, 80, waves_font_20, "mm")
            else:
                role_bg_draw.text(
                    (base_x + 100, 80),
                    f"{team_info.score}",
                    team_color,
                    waves_font_20,
                    "mm",
                )

        card_img.paste(role_bg, (0, 510 + rank_temp_index * item_spacing), role_bg)

    card_img = add_footer(card_img)
    card_img = await convert_img(card_img)

    logger.info(f"[draw_matrix_rank_list] end: {time.time() - start_time}")
    return card_img
