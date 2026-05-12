"""rank 子目录下各排行 PIL 渲染分档颜色 + 水晶炫彩绘制

按 (功能, 排行类型) 区分命名，**勿混用**——不同玩法 / 不同范围（总/群）阈值不同：
- 矩阵 总排行 (matrix total)
- 矩阵 群排行 (matrix local)
- 深塔 总排行 (slash total)
- 深塔 群排行 (slash local)

最高档使用 CRYSTAL_SENTINEL 触发 `draw_crystal_text` 走渐变。
"""

import math

from PIL import Image, ImageDraw


CRYSTAL_SENTINEL = (-1, -1, -1)

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


def get_matrix_total_rank_color(score: int) -> tuple:
    """矩阵 总排行 分档颜色。配色与 detail / 群排行一致，仅阈值不同"""
    if score >= 500000:
        return CRYSTAL_SENTINEL
    if score >= 300000:
        return (255, 82, 82)
    if score >= 45000:
        return (255, 213, 79)
    if score >= 21000:
        return (206, 147, 216)
    if score >= 12000:
        return (100, 200, 255)
    return (138, 138, 138)


def get_matrix_local_rank_color(score: int) -> tuple:
    """矩阵 群排行 分档颜色。与 detail 共用同一份阈值 + 配色"""
    if score >= 200000:
        return CRYSTAL_SENTINEL
    if score >= 150000:
        return (255, 82, 82)
    if score >= 45000:
        return (255, 213, 79)
    if score >= 21000:
        return (206, 147, 216)
    if score >= 12000:
        return (100, 200, 255)
    return (138, 138, 138)


def get_slash_total_rank_color(score: int) -> tuple:
    """深塔 总排行 分档颜色"""
    if score >= 30000:
        return (255, 0, 0)
    if score >= 25000:
        return (234, 183, 4)
    if score >= 20000:
        return (185, 106, 217)
    if score >= 15000:
        return (22, 145, 121)
    if score >= 10000:
        return (53, 152, 219)
    return (255, 255, 255)


def get_slash_local_rank_color(score: int) -> tuple:
    """深塔 群排行 分档颜色"""
    if score >= 30000:
        return (255, 0, 0)
    if score >= 20000:
        return (234, 183, 4)
    if score >= 10000:
        return (185, 106, 217)
    if score >= 5500:
        return (22, 145, 121)
    if score >= 4500:
        return (53, 152, 219)
    return (200, 200, 200)
