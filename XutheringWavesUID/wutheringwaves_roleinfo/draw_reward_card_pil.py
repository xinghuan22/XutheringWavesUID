import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.api.model import AccountBaseInfo
from ..utils.fonts.waves_fonts import (
    waves_font_16,
    waves_font_18,
    waves_font_20,
    waves_font_22,
    waves_font_25,
    waves_font_26,
    waves_font_30,
    waves_font_42,
    waves_font_70,
)
from ..utils.image import (
    GOLD,
    GREY,
    add_footer,
    get_waves_bg,
)
from ..utils.imagetool import draw_pic_with_ring


TEXT_PATH = Path(__file__).parent / "texture2d"
WIDTH = 1000
MARGIN = 35
CARD_BG = (18, 20, 24, 214)
CARD_BG_DARK = (10, 11, 14, 226)
LINE = (255, 255, 255, 34)
WHITE = (245, 245, 245, 255)


def _decode_data_url(data_url: str, size: int) -> Image.Image:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    img = Image.open(BytesIO(base64.b64decode(data_url))).convert("RGBA")
    return img.resize((size, size))


def _fit_text(text: str, font, max_width: int) -> str:
    text = str(text)
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(f"{text}...") > max_width:
        text = text[:-1]
    return f"{text}..." if text else ""


def _wrap_text(text: str, font, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for char in str(text):
        if font.getlength(current + char) <= max_width:
            current += char
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines or [""]


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: object,
    font,
    fill=WHITE,
    anchor: str | None = None,
) -> None:
    draw.text(xy, str(text), font=font, fill=fill, anchor=anchor)


def _rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill=CARD_BG,
    outline=LINE,
    radius: int = 16,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


async def _draw_header(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    score_data: Dict,
    ev: Event,
) -> None:
    account_info: AccountBaseInfo = score_data["account_info"]

    try:
        base_info_bg = Image.open(TEXT_PATH / "base_info_bg.png").convert("RGBA")
        base_info_draw = ImageDraw.Draw(base_info_bg, "RGBA")
        base_info_draw.text((275, 120), f"{account_info.name[:10]}", "white", waves_font_30, "lm")
        base_info_draw.text(
            (226, 173),
            f"特征码:  {score_data['display_uid']}",
            GOLD,
            waves_font_25,
            "lm",
        )
        card.paste(base_info_bg, (35, 0), base_info_bg)
    except Exception:
        _rounded_card(draw, (MARGIN, 15, WIDTH - MARGIN, 225), CARD_BG)
        _draw_text(draw, (220, 76), _fit_text(account_info.name, waves_font_42, 430), waves_font_42)
        _draw_text(draw, (220, 128), f"UID {score_data['display_uid']}", waves_font_25, GOLD)

    try:
        avatar, avatar_ring = await draw_pic_with_ring(ev)
        card.paste(avatar, (45, 50), avatar)
        card.paste(avatar_ring, (55, 60), avatar_ring)
    except Exception:
        pass

    if account_info.is_full:
        try:
            title_bar = Image.open(TEXT_PATH / "title_bar.png").convert("RGBA")
            title_bar_draw = ImageDraw.Draw(title_bar, "RGBA")
            title_bar_draw.text((660, 125), "账号等级", GREY, waves_font_26, "mm")
            title_bar_draw.text((660, 78), f"Lv.{account_info.level}", "white", waves_font_42, "mm")
            title_bar_draw.text((810, 125), "世界等级", GREY, waves_font_26, "mm")
            title_bar_draw.text((810, 78), f"Lv.{account_info.worldLevel}", "white", waves_font_42, "mm")
            card.paste(title_bar, (0, 50), title_bar)
        except Exception:
            pass


def _draw_score_line(
    draw: ImageDraw.ImageDraw,
    y: int,
    label: str,
    value: str,
    x1: int = 350,
    x2: int = 930,
) -> None:
    _draw_text(draw, (x1, y), label, waves_font_22, (225, 225, 225, 245), "lm")
    _draw_text(draw, (x2, y), value, waves_font_30, GOLD, "rm")


def _draw_char_weapon_score_line(
    draw: ImageDraw.ImageDraw,
    y: int,
    score_data: Dict,
) -> None:
    _draw_text(draw, (350, y), "共鸣者 + 武器积分", waves_font_22, (225, 225, 225, 245), "lm")

    raw_total = score_data["char_weapon_total_raw"]
    capped_total = score_data["char_weapon_total_capped"]
    final_score = capped_total if raw_total > 8000 else raw_total
    op = "->" if raw_total > 8000 else "="

    final_text = str(final_score)
    final_w = waves_font_30.getlength(final_text)
    _draw_text(draw, (930, y), final_text, waves_font_30, GOLD, "rm")

    op_x = int(930 - final_w - 26)
    _draw_text(draw, (op_x, y), op, waves_font_22, GREY, "rm")

    detail_text = f"{score_data['char_score_raw']} + {score_data['weapon_score_raw']}"
    detail_right = op_x - 22
    detail_text = _fit_text(detail_text, waves_font_20, max(120, detail_right - 570))
    _draw_text(draw, (detail_right, y), detail_text, waves_font_20, (185, 188, 194, 245), "rm")


def _draw_unlock_progress(draw: ImageDraw.ImageDraw, y: int, total_score: int) -> None:
    _draw_text(draw, (70, y), "当前解锁进度", waves_font_20, (180, 180, 180, 235), "lm")
    bar_x, bar_y, bar_w, bar_h = 235, y + 46, 670, 8
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=4, fill=(255, 255, 255, 28))
    pct = min(1, max(0, total_score / 10000))
    fill_w = int(bar_w * pct)
    if fill_w:
        draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=4, fill=GOLD)

    for value, label, reward in [
        (1000, "1000", "10个唤声涡纹"),
        (3000, "3000", "羁旅印章"),
        (5000, "5000", "寰星之律称号"),
        (7500, "7500", "10个浮金波纹"),
        (10000, "10000", "缀星纺宙之锤"),
    ]:
        x = bar_x + int(bar_w * value / 10000)
        reached = total_score >= value
        dot_fill = GOLD if reached else (60, 60, 60, 255)
        dot_outline = (255, 255, 255, 220) if reached else (110, 110, 110, 180)
        anchor = "mm"
        reward_x = x
        if value == 10000:
            anchor = "rm"
            reward_x = x + 5
        _draw_text(
            draw,
            (reward_x, bar_y - 24),
            reward,
            waves_font_16,
            GOLD if reached else (155, 158, 166, 230),
            anchor,
        )
        draw.ellipse((x - 6, bar_y - 2, x + 6, bar_y + 10), fill=dot_fill, outline=dot_outline, width=2)
        _draw_text(draw, (x, bar_y + 27), label, waves_font_18, GOLD if reached else GREY, "mm")


def _draw_summary(draw: ImageDraw.ImageDraw, y: int, score_data: Dict) -> int:
    x, w, h = MARGIN, WIDTH - MARGIN * 2, 384
    _rounded_card(draw, (x, y, x + w, y + h), CARD_BG, radius=6)

    header_y = y + 36
    _draw_text(draw, (x + 30, header_y), "伴行积分", waves_font_30, WHITE, "lm")
    draw.line((x + 165, header_y, x + w - 170, header_y), fill=(212, 177, 99, 120), width=1)
    _draw_text(draw, (x + w - 30, header_y), "COMPANION", waves_font_18, (138, 142, 150, 255), "rm")

    score_y = y + 104
    draw.line((x + 38, score_y - 38, x + 38, score_y + 54), fill=GOLD, width=3)
    _draw_text(draw, (x + 58, score_y - 34), "总分", waves_font_20, (138, 142, 150, 255), "lm")
    _draw_text(draw, (x + 56, score_y + 38), score_data["total_score"], waves_font_70, GOLD, "lm")

    _draw_char_weapon_score_line(draw, y + 92, score_data)
    draw.line((350, y + 122, 930, y + 122), fill=(212, 177, 99, 46), width=1)

    achievement_value = f"{score_data['achievement_score']}"
    active_value = f"{score_data['active_days_score']}"
    _draw_score_line(draw, y + 156, f"成就({score_data['achievement_count']})", achievement_value)
    _draw_score_line(draw, y + 198, f"活跃({score_data['active_days']}天)", active_value)

    draw.line((x + 28, y + 238, x + w - 28, y + 238), fill=(255, 255, 255, 24), width=1)
    _draw_unlock_progress(draw, y + 266, int(score_data["total_score"]))
    return y + h + 24


def _draw_section_title(draw: ImageDraw.ImageDraw, y: int, title: str, total: object) -> None:
    _draw_text(draw, (MARGIN, y), title, waves_font_30, WHITE)
    _draw_text(draw, (WIDTH - MARGIN, y + 2), f"{total} 分", waves_font_26, GOLD, "ra")


def _draw_empty(draw: ImageDraw.ImageDraw, y: int) -> None:
    _rounded_card(draw, (MARGIN, y, WIDTH - MARGIN, y + 74), CARD_BG)
    _draw_text(draw, (WIDTH // 2, y + 37), "暂无可计分项目", waves_font_25, GREY, "mm")


def _draw_reward_item(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: Dict,
    x: int,
    y: int,
    w: int,
) -> None:
    _rounded_card(draw, (x, y, x + w, y + 108), CARD_BG_DARK, radius=14)
    try:
        icon = _decode_data_url(item["icon_url"], 76)
        card.alpha_composite(icon, (x + 16, y + 16))
    except Exception:
        draw.rounded_rectangle((x + 16, y + 16, x + 92, y + 92), radius=10, fill=(36, 38, 44, 255))

    name = _fit_text(item["name"], waves_font_25, w - 130)
    _draw_text(draw, (x + 108, y + 16), name, waves_font_25)
    _draw_text(draw, (x + 108, y + 50), item["detail"], waves_font_20, GREY)
    _draw_text(draw, (x + w - 18, y + 76), item["score"], waves_font_30, GOLD, "ra")


def _draw_reward_grid(
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    items: List[Dict],
    y: int,
    title: str,
    total: object,
) -> int:
    _draw_section_title(draw, y, title, total)
    y += 44
    if not items:
        _draw_empty(draw, y)
        return y + 98

    cols = 3
    gap = 16
    item_w = (WIDTH - MARGIN * 2 - gap * (cols - 1)) // cols
    for idx, item in enumerate(items):
        row = idx // cols
        col = idx % cols
        x = MARGIN + col * (item_w + gap)
        item_y = y + row * 118
        _draw_reward_item(card, draw, item, x, item_y, item_w)
    rows = (len(items) + cols - 1) // cols
    return y + rows * 118 + 20


def _draw_bullet_list(
    draw: ImageDraw.ImageDraw,
    items: List[str],
    x: int,
    y: int,
    max_width: int,
) -> int:
    for item in items:
        draw.ellipse((x, y + 10, x + 6, y + 16), fill=(212, 177, 99, 180))
        lines = _wrap_text(item, waves_font_18, max_width - 18)
        for idx, line in enumerate(lines):
            _draw_text(draw, (x + 18, y + 14 + idx * 24), line, waves_font_18, WHITE, "lm")
        y += max(1, len(lines)) * 24 + 8
    return y


def _draw_disclaimer(draw: ImageDraw.ImageDraw, y: int) -> int:
    x, w, h = MARGIN, WIDTH - MARGIN * 2, 430
    _rounded_card(draw, (x, y, x + w, y + h), CARD_BG, radius=6)

    header_y = y + 36
    _draw_text(draw, (x + 30, header_y), "计分说明", waves_font_30, WHITE, "lm")
    draw.line((x + 165, header_y, x + w - 170, header_y), fill=(212, 177, 99, 120), width=1)
    _draw_text(draw, (x + w - 30, header_y), "DISCLAIMER", waves_font_18, (138, 142, 150, 255), "rm")

    left_x = x + 36
    right_x = x + 496
    list_y = y + 86
    _draw_text(draw, (left_x, list_y), "计分规则", waves_font_22, GOLD, "lm")
    _draw_text(draw, (right_x, list_y), "特别说明", waves_font_22, GOLD, "lm")

    _draw_bullet_list(
        draw,
        [
            "活跃天数：每天10分（上限10000分）",
            "成就：每个2分（上限1600分）",
            "共鸣者+武器上限8000分",
            "获得5星共鸣者（可重复获得，漂泊者除外）：100分",
            "获得5星武器（活动获取武器除外）：100分",
        ],
        left_x,
        list_y + 34,
        410,
    )
    _draw_bullet_list(
        draw,
        [
            "由于数据原因，以上数据未计算溢出和未点亮的共鸣链",
            "同一武器在多角色面板可能重复计算，武器需先装备至角色才能计算",
            "1.2赠送相里要和45级赠送武器未扣除，但实际如何计算未知",
            "活跃天数刷新为北京时间0点",
        ],
        right_x,
        list_y + 34,
        410,
    )

    draw.line((x + 30, y + h - 58, x + w - 30, y + h - 58), fill=(255, 255, 255, 24), width=1)
    _draw_text(
        draw,
        (WIDTH // 2, y + h - 30),
        "本积分计算数据非来自官方，可能与最终游戏内积分有出入，最终解释权归库洛所有。",
        waves_font_16,
        (170, 174, 184, 245),
        "mm",
    )
    return y + h + 24


async def draw_reward_img_pil(
    score_data: Dict,
    ev: Event,
) -> bytes:
    character_items = score_data["character_items"]
    weapon_items = score_data["weapon_items"]
    char_rows = max(1, (len(character_items) + 2) // 3)
    weapon_rows = max(1, (len(weapon_items) + 2) // 3)
    summary_start = 265
    summary_height = 408
    disclaimer_height = 454
    section_height = (44 + char_rows * 118 + 20) + 8 + (44 + weapon_rows * 118 + 20)
    height = summary_start + summary_height + section_height + disclaimer_height + 50

    card = get_waves_bg(WIDTH, height, "bg3")
    if card.mode != "RGBA":
        card = card.convert("RGBA")
    draw = ImageDraw.Draw(card, "RGBA")

    await _draw_header(card, draw, score_data, ev)
    y = _draw_summary(draw, summary_start, score_data)
    y = _draw_reward_grid(
        card,
        draw,
        character_items,
        y,
        "五星角色积分",
        score_data["char_score_raw"],
    )
    y = _draw_reward_grid(
        card,
        draw,
        weapon_items,
        y + 8,
        "五星武器积分",
        score_data["weapon_score_raw"],
    )
    y = _draw_disclaimer(draw, y + 8)

    add_footer(card, w=600, offset_y=25)
    return await convert_img(card)
