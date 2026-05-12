from typing import Union
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import crop_center_img

from ..utils.util import hide_uid
from ..utils.api.model import AccountBaseInfo, MatrixDetail
from ..utils.imagetool import draw_pic_with_ring
from ..utils.resource.RESOURCE_PATH import MATRIX_PATH
from ..utils.image import (
    GOLD,
    GREY,
    SPECIAL_GOLD,
    CHAIN_COLOR,
    add_footer,
    clean_alpha_matte,
    get_waves_bg,
    make_smooth_rounded_mask,
    pic_download_from_url,
)
from ._colors import (
    CRYSTAL_SENTINEL,
    GOLD_LINE as PIL_LINE,
    PANEL_FILL as PIL_PANEL_FILL,
    PANEL_OUTLINE as PIL_PANEL_OUTLINE,
    draw_crystal_text,
    get_matrix_score_color,
)
from ..utils.fonts.waves_fonts import (
    draw_text_with_fallback,
    waves_font_18,
    waves_font_20,
    waves_font_24,
    waves_font_25,
    waves_font_26,
    waves_font_28,
    waves_font_30,
    waves_font_32,
    waves_font_36,
    waves_font_42,
)
from .period import get_matrix_period_number

TEXT_PATH = Path(__file__).parent / "texture2d"

MODE_NAME_MAP = {
    1: "奇点扩张",
    0: "稳态协议",
}

PIL_CARD_WIDTH = 1000
PIL_HEADER_HEIGHT = 260
MATRIX_ERROR_NO_DATA = "当前暂无终焉矩阵数据"


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple, text: object, fill, font, anchor=None):
    draw_text_with_fallback(
        draw,
        xy,
        "" if text is None else str(text),
        fill=fill,
        font=font,
        anchor=anchor,
    )


def _load_texture(name: str) -> Union[Image.Image, None]:
    path = TEXT_PATH / name
    if not path.exists():
        return None
    return Image.open(path).convert("RGBA")


def _load_texture_cover(name: str, width: int, height: int, fallback_bg: str = "bg9") -> Image.Image:
    img = _load_texture(name)
    if img is None:
        return get_waves_bg(width, height, fallback_bg)
    return crop_center_img(img, width, height)


def _draw_panel(
    img: Image.Image,
    xy: tuple,
    size: tuple,
    radius: int = 14,
    fill: tuple = PIL_PANEL_FILL,
    outline: tuple = PIL_PANEL_OUTLINE,
    width: int = 1,
) -> None:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel, "RGBA")
    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1),
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )
    img.alpha_composite(panel, xy)


def _paste_rounded_image(
    base: Image.Image,
    image: Image.Image,
    xy: tuple,
    size: tuple,
    radius: int = 8,
):
    image = clean_alpha_matte(image, (42, 46, 53, 255))
    image = crop_center_img(image, size[0], size[1])
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(image, (0, 0))

    mask = make_smooth_rounded_mask(size, radius)
    alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    layer.putalpha(alpha)
    base.alpha_composite(layer, xy)


def _paste_contain_rounded_image(
    base: Image.Image,
    image: Image.Image,
    xy: tuple,
    size: tuple,
    radius: int = 6,
    padding: int = 4,
):
    image = clean_alpha_matte(image, (8, 11, 15, 255))
    max_w = max(1, size[0] - padding * 2)
    max_h = max(1, size[1] - padding * 2)
    image.thumbnail((max_w, max_h), Image.LANCZOS)

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(
        image,
        ((size[0] - image.width) // 2, (size[1] - image.height) // 2),
    )

    mask = make_smooth_rounded_mask(size, radius)
    alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    layer.putalpha(alpha)
    base.alpha_composite(layer, xy)


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    size: tuple,
    pct: float,
):
    x, y = xy
    w, h = size
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(50, 64, 75, 210))
    fill_w = max(0, min(w, int(w * pct / 100)))
    if fill_w:
        draw.rounded_rectangle(
            (x, y, x + fill_w, y + h),
            radius=h // 2,
            fill=(212, 177, 99, 230),
        )


async def _draw_user_header(
    card_img: Image.Image,
    ev: Event,
    account_info: AccountBaseInfo,
    user_pref: str,
):
    draw = ImageDraw.Draw(card_img, "RGBA")

    base_info_bg = _load_texture("base_info_bg.png")
    if base_info_bg:
        base_info_draw = ImageDraw.Draw(base_info_bg, "RGBA")
        _draw_text(base_info_draw, (275, 120), account_info.name[:10], "white", waves_font_30, "lm")
        _draw_text(
            base_info_draw,
            (226, 173),
            f"特征码:  {hide_uid(account_info.id, user_pref=user_pref)}",
            GOLD,
            waves_font_25,
            "lm",
        )
        card_img.alpha_composite(base_info_bg, (15, 20))
    else:
        _draw_panel(card_img, (25, 35), (560, 170), radius=16)
        _draw_text(draw, (210, 90), account_info.name[:10], "white", waves_font_36, "lm")
        _draw_text(
            draw,
            (210, 140),
            f"UID {hide_uid(account_info.id, user_pref=user_pref)}",
            GOLD,
            waves_font_26,
            "lm",
        )

    try:
        avatar, avatar_ring = await draw_pic_with_ring(ev)
        card_img.alpha_composite(avatar, (25, 70))
        card_img.alpha_composite(avatar_ring, (35, 80))
    except Exception as e:
        logger.warning(f"[鸣潮] 矩阵PIL头像绘制失败: {e}")

    if account_info.is_full:
        title_bar = _load_texture("title_bar.png")
        if title_bar:
            title_draw = ImageDraw.Draw(title_bar, "RGBA")
            _draw_text(title_draw, (660, 125), "账号等级", GREY, waves_font_26, "mm")
            _draw_text(title_draw, (660, 78), f"Lv.{account_info.level}", "white", waves_font_42, "mm")
            _draw_text(title_draw, (810, 125), "世界等级", GREY, waves_font_26, "mm")
            _draw_text(title_draw, (810, 78), f"Lv.{account_info.worldLevel}", "white", waves_font_42, "mm")
            card_img.paste(title_bar, (-20, 70), title_bar)

    _draw_text(draw, (PIL_CARD_WIDTH // 2, 50), f"第{get_matrix_period_number()}期", "white", waves_font_30, "mm")


async def draw_matrix_index_img(
    ev: Event,
    account_info: AccountBaseInfo,
    user_pref: str,
    current_date: str,
    matrix_detail: MatrixDetail,
) -> bytes:
    modes = [
        mode
        for mode in sorted(matrix_detail.modeDetails, key=lambda m: m.modeId, reverse=True)
        if mode.hasRecord
    ]
    if not modes:
        raise ValueError(MATRIX_ERROR_NO_DATA)

    section_h = 76 + len(modes) * 116
    card_h = PIL_HEADER_HEIGHT + section_h + 55
    card_img = _load_texture_cover("matrix-home-bg.png", PIL_CARD_WIDTH, card_h)
    card_img.alpha_composite(Image.new("RGBA", card_img.size, (0, 0, 0, 45)), (0, 0))

    await _draw_user_header(card_img, ev, account_info, user_pref)
    draw = ImageDraw.Draw(card_img, "RGBA")

    section_y = PIL_HEADER_HEIGHT
    _draw_panel(card_img, (40, section_y), (920, section_h), radius=14)
    _draw_text(draw, (70, section_y + 38), "终焉矩阵", "white", waves_font_32, "lm")
    draw.line((210, section_y + 38, 790, section_y + 38), fill=PIL_LINE, width=2)
    _draw_text(draw, (930, section_y + 38), current_date, (180, 180, 180), waves_font_20, "rm")

    reward_icon = _load_texture("reward.png")
    for idx, mode in enumerate(modes):
        row_y = section_y + 76 + idx * 116
        draw.line((64, row_y, 936, row_y), fill=(255, 255, 255, 24), width=1)

        rank_img = _load_texture(f"rank-{max(0, min(mode.rank, 7))}.png")
        if rank_img:
            rank_img.thumbnail((120, 86), Image.LANCZOS)
            card_img.alpha_composite(rank_img, (75, row_y + 14))

        mode_name = MODE_NAME_MAP.get(mode.modeId, f"模式{mode.modeId}")
        _draw_text(draw, (205, row_y + 56), mode_name, GOLD, waves_font_32, "lm")
        score_color = get_matrix_score_color(mode.score)
        if score_color == CRYSTAL_SENTINEL:
            draw_crystal_text(card_img, str(mode.score), 420, row_y + 56, waves_font_42, "lm")
        else:
            _draw_text(draw, (420, row_y + 56), mode.score, score_color, waves_font_42, "lm")

        if reward_icon:
            icon = reward_icon.resize((42, 42), Image.LANCZOS)
            card_img.alpha_composite(icon, (690, row_y + 35))
        _draw_text(
            draw,
            (920, row_y + 57),
            f"奖励 {matrix_detail.reward}/{matrix_detail.totalReward}",
            GOLD,
            waves_font_28,
            "rm",
        )

    card_img = add_footer(card_img, 600, 20)
    return await convert_img(card_img)


async def draw_matrix_detail_img(
    ev: Event,
    account_info: AccountBaseInfo,
    user_pref: str,
    current_date: str,
    matrix_detail: MatrixDetail,
    role_detail_info_map: dict,
    target_mode_id: int = 1,
    char_ids_map: dict = None,
) -> bytes:
    mode = next(
        (
            item
            for item in matrix_detail.modeDetails
            if item.modeId == target_mode_id and item.hasRecord and item.teams
        ),
        None,
    )
    if not mode:
        raise ValueError(MATRIX_ERROR_NO_DATA)

    teams = mode.teams or []
    team_h = 122
    section_h = 64 + 162 + len(teams) * (team_h + 10) + 22
    card_h = PIL_HEADER_HEIGHT + section_h + 55
    card_img = _load_texture_cover(
        f"matrix-detail-bg-{target_mode_id}.png",
        PIL_CARD_WIDTH,
        card_h,
    )
    card_img.alpha_composite(Image.new("RGBA", card_img.size, (0, 0, 0, 35)), (0, 0))

    await _draw_user_header(card_img, ev, account_info, user_pref)
    draw = ImageDraw.Draw(card_img, "RGBA")

    role_detail_info_map = role_detail_info_map if role_detail_info_map else {}
    _char_ids_map = char_ids_map or {}

    section_y = PIL_HEADER_HEIGHT
    _draw_panel(card_img, (40, section_y), (920, section_h), radius=14)
    mode_name = MODE_NAME_MAP.get(mode.modeId, f"模式{mode.modeId}")
    _draw_text(draw, (70, section_y + 34), mode_name, "white", waves_font_32, "lm")
    draw.line((220, section_y + 34, 790, section_y + 34), fill=PIL_LINE, width=2)
    _draw_text(draw, (930, section_y + 34), current_date, (180, 180, 180), waves_font_20, "rm")

    overview_y = section_y + 64
    overview_bg = _load_texture_cover("overview-bg.png", 880, 142)
    _paste_rounded_image(card_img, overview_bg, (60, overview_y), (880, 142), radius=10)
    draw.rounded_rectangle(
        (60, overview_y, 940, overview_y + 142),
        radius=10,
        outline=(43, 64, 77, 180),
        width=1,
    )

    rank_detail = _load_texture(f"rank-detail-{max(0, min(mode.rank, 7))}.png")
    if rank_detail:
        rank_detail = rank_detail.resize((400, 400), Image.LANCZOS)
        rank_layer = Image.new("RGBA", (880, 142), (0, 0, 0, 0))
        rank_layer.alpha_composite(rank_detail, (-80, -129))
        card_img.alpha_composite(rank_layer, (60, overview_y))

    boss_count = mode.bossCount or 0
    pass_boss = mode.passBoss or 0
    progress_pct = (pass_boss / boss_count * 100) if boss_count > 0 else 0
    score_x = 400
    _draw_text(draw, (score_x, overview_y + 42), "累计积分", "white", waves_font_28, "lm")
    score_color = get_matrix_score_color(mode.score)
    if score_color == CRYSTAL_SENTINEL:
        draw_crystal_text(card_img, str(mode.score), 900, overview_y + 42, waves_font_42, "rm")
    else:
        _draw_text(draw, (900, overview_y + 42), mode.score, score_color, waves_font_42, "rm")
    draw.line((score_x, overview_y + 72, 905, overview_y + 72), fill=(212, 177, 99, 100), width=1)
    _draw_text(draw, (score_x, overview_y + 100), "挑战进度", "white", waves_font_24, "lm")
    _draw_text(draw, (900, overview_y + 100), f"{pass_boss}/{boss_count}", "white", waves_font_24, "rm")
    _draw_progress_bar(draw, (score_x, overview_y + 116), (505, 10), progress_pct)

    boss_icon = _load_texture("boss.png")
    matrix_score_icon = _load_texture("matrix_score.png")

    for team_idx, team in enumerate(teams):
        row_y = overview_y + 162 + team_idx * (team_h + 10)
        _draw_panel(
            card_img,
            (60, row_y),
            (880, team_h),
            radius=10,
            fill=(24, 35, 48, 168),
            outline=(255, 255, 255, 24),
        )

        _draw_text(draw, (88, row_y + team_h // 2), f"{team_idx + 1:02d}", "white", waves_font_36, "lm")
        _draw_text(draw, (160, row_y + team_h // 2), ">", (255, 255, 255, 110), waves_font_30, "mm")

        team_char_ids = _char_ids_map.get((mode.modeId, team_idx), [])
        role_x = 188
        for role_idx in range(3):
            box_x = role_x + role_idx * 98
            box_y = row_y + 20
            draw.rounded_rectangle(
                (box_x, box_y, box_x + 82, box_y + 82),
                radius=8,
                fill=(42, 46, 53, 220),
                outline=(255, 255, 255, 16),
                width=1,
            )

            icon_url = team.roleIcons[role_idx] if role_idx < len(team.roleIcons) else ""
            if icon_url:
                try:
                    role_img = await pic_download_from_url(MATRIX_PATH, icon_url)
                    _paste_rounded_image(card_img, role_img, (box_x, box_y), (82, 82), radius=8)
                except Exception as e:
                    logger.warning(f"[鸣潮] 矩阵PIL角色头像下载失败: {e}")
            else:
                _draw_text(draw, (box_x + 41, box_y + 34), "模版", (180, 180, 180), waves_font_18, "mm")
                _draw_text(draw, (box_x + 41, box_y + 58), "角色", (180, 180, 180), waves_font_18, "mm")

            chain_num = None
            chain_name = ""
            if role_idx < len(team_char_ids) and team_char_ids[role_idx]:
                char_id = team_char_ids[role_idx]
                if str(char_id) in role_detail_info_map:
                    temp = role_detail_info_map[str(char_id)]
                    chain_num = temp.get_chain_num()
                    chain_name = temp.get_chain_name()

            if chain_name:
                chain_color = CHAIN_COLOR.get(chain_num or 0, (149, 165, 166))
                draw.rounded_rectangle(
                    (box_x + 40, box_y + 59, box_x + 82, box_y + 82),
                    radius=4,
                    fill=(0, 0, 0, 190),
                )
                draw.rectangle((box_x + 78, box_y + 59, box_x + 82, box_y + 82), fill=chain_color)
                _draw_text(draw, (box_x + 76, box_y + 70), chain_name, "white", waves_font_18, "rm")

        divider_x = 514
        draw.line((divider_x, row_y + 28, divider_x, row_y + 94), fill=(255, 255, 255, 35), width=2)

        buff_x = 544
        if team.buffs and team.buffs[0].buffIcon:
            draw.rounded_rectangle(
                (buff_x, row_y + 33, buff_x + 56, row_y + 89),
                radius=6,
                fill=(8, 11, 15, 140),
                outline=(115, 140, 163, 70),
                width=1,
            )
            try:
                buff_img = await pic_download_from_url(MATRIX_PATH, team.buffs[0].buffIcon)
                _paste_contain_rounded_image(card_img, buff_img, (buff_x, row_y + 33), (56, 56), radius=6)
            except Exception as e:
                logger.warning(f"[鸣潮] 矩阵PIL增益图标下载失败: {e}")

        round_center_x = 696
        _draw_text(draw, (round_center_x, row_y + 44), f"第{team.round}轮", "white", waves_font_26, "mm")
        boss_box = (round_center_x - 58, row_y + 62, round_center_x + 58, row_y + 96)
        draw.rounded_rectangle(
            boss_box,
            radius=17,
            fill=(8, 11, 15, 130),
            outline=(255, 255, 255, 28),
            width=1,
        )
        if boss_icon:
            icon = boss_icon.resize((40, 40), Image.LANCZOS)
            card_img.alpha_composite(icon, (boss_box[0] - 5, row_y + 59))
        pass_text = f"{team.passBoss}"
        total_text = f"/{team.bossCount}"
        pass_w = waves_font_24.getlength(pass_text)
        total_w = waves_font_24.getlength(total_text)
        count_x = round_center_x - (pass_w + total_w) / 2 + 5
        _draw_text(draw, (count_x, row_y + 79), pass_text, "white", waves_font_24, "lm")
        _draw_text(draw, (count_x + pass_w, row_y + 79), total_text, (138, 138, 138), waves_font_24, "lm")

        if matrix_score_icon:
            score_icon = matrix_score_icon.resize((36, 36), Image.LANCZOS)
            card_img.alpha_composite(score_icon, (838, row_y + 24))
        _draw_text(draw, (850, row_y + 82), f"+{team.score}", SPECIAL_GOLD, waves_font_32, "mm")

    card_img = add_footer(card_img, 600, 20)
    return await convert_img(card_img)
