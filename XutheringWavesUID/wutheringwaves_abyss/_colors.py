"""abyss 子目录下 matrix / slash / abyss / challenge PIL 渲染共用的颜色常量与配色绘制

数值对齐对应 HTML 模板（matrix_card.html、slash_card.html、challenge_card.html）的样式，
确保 PIL 与 HTML 渲染视觉一致。
"""

import math

from PIL import Image, ImageDraw


PANEL_FILL = (15, 17, 21, 115)
PANEL_OUTLINE = (255, 255, 255, 15)
GOLD_LINE = (212, 177, 99, 150)


# 终焉矩阵 score 分档：(下限 score, HTML CSS 类名, PIL RGB) — 仅矩阵用，别给其它玩法
# top tier (score-rainbow) PIL 用 CRYSTAL_SENTINEL 触发 draw_crystal_text 走渐变
CRYSTAL_SENTINEL = (-1, -1, -1)

MATRIX_SCORE_TIERS = (
    (200000, "score-rainbow", CRYSTAL_SENTINEL),
    (150000, "score-red", (255, 82, 82)),
    (45000, "score-gold", (255, 213, 79)),
    (21000, "score-purple", (206, 147, 216)),
    (12000, "score-blue", (100, 200, 255)),
)
MATRIX_SCORE_DEFAULT_CLASS = "score-grey"
MATRIX_SCORE_DEFAULT_RGB = (138, 138, 138)


def get_matrix_score_color(score: int) -> tuple:
    """矩阵 score → PIL RGB；最高档返回 CRYSTAL_SENTINEL，调用方需走 draw_crystal_text"""
    for threshold, _cls, color in MATRIX_SCORE_TIERS:
        if score >= threshold:
            return color
    return MATRIX_SCORE_DEFAULT_RGB


def get_matrix_score_class(score: int) -> str:
    """矩阵 score → HTML CSS 类名"""
    for threshold, cls, _color in MATRIX_SCORE_TIERS:
        if score >= threshold:
            return cls
    return MATRIX_SCORE_DEFAULT_CLASS


# 矩阵最高档"水晶炫彩"渐变用色（HTML score-rainbow 等价物）
CRYSTAL_COLORS = (
    (255, 120, 180),
    (180, 120, 255),
    (100, 200, 255),
    (120, 255, 200),
    (255, 230, 100),
    (255, 150, 100),
    (255, 120, 180),
)


def draw_crystal_text(img: Image.Image, text: str, x: int, y: int, font, anchor: str = "lm") -> None:
    """在 img 上绘制水晶炫彩文字（横向渐变 + 竖向 sin 调亮）"""
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    if tw <= 0 or th <= 0:
        return

    if "m" in anchor:
        if anchor == "mm":
            x -= tw // 2
            y -= th // 2
        elif anchor == "lm":
            y -= th // 2
        elif anchor == "rm":
            x -= tw
            y -= th // 2

    gradient = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    for px in range(tw):
        ratio = px / tw
        seg = ratio * (len(CRYSTAL_COLORS) - 1)
        idx = min(int(seg), len(CRYSTAL_COLORS) - 2)
        frac = seg - idx
        c1, c2 = CRYSTAL_COLORS[idx], CRYSTAL_COLORS[idx + 1]
        r = int(c1[0] + (c2[0] - c1[0]) * frac)
        g = int(c1[1] + (c2[1] - c1[1]) * frac)
        b = int(c1[2] + (c2[2] - c1[2]) * frac)
        for py in range(th):
            brightness = 0.7 + 0.3 * math.sin(py / th * math.pi)
            gradient.putpixel(
                (px, py),
                (
                    min(255, int(r * brightness)),
                    min(255, int(g * brightness)),
                    min(255, int(b * brightness)),
                    255,
                ),
            )

    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).text((0, 0), text, fill=255, font=font, anchor="lt")

    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    result.paste(gradient, (0, 0), mask)
    img.alpha_composite(result, (x, y))
