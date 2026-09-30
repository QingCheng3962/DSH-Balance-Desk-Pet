# -*- coding: utf-8 -*-
"""原版气泡的 SVG 栅格化 —— **直接使用 whale-widget.js 里的原始数据**。

源码（assets/whale-widget.js:11552）：

    <svg viewBox="0 0 1026 700" preserveAspectRatio="xMidYMid meet">
      <path class="dshwv-bshape" fill="#FFFFFF" stroke="#203170" stroke-width="18"
            stroke-linejoin="round" stroke-linecap="round"
            d="M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465
               A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z"/>
      <ellipse class="dshwv-b1" cx="352" cy="561" rx="37.5" ry="26" .../>
      <ellipse class="dshwv-b2" cx="442" cy="646" rx="24.5" ry="18" .../>
    </svg>

    .dshwv-text{left:44.25%;top:36%;width:66%;height:64%;color:#536ba9;line-height:1.15}

这里做的事：把上面的 path / ellipse / 文字区域**原样**搬成 Pillow 绘制，
不做任何"照着眼睛画"的近似。SVG 的 A（椭圆弧）按 SVG 规范 F.6.5 的
端点参数化换算成中心参数化，再展平成折线；描边用圆角连接模拟
stroke-linejoin/linecap="round"。
"""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# ---- 原样搬过来的常量 -------------------------------------------------------
BALLOON_VIEWBOX = (1026.0, 700.0)                  # viewBox="0 0 1026 700"
BALLOON_PATH = ("M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465 "
                "A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z")
BALLOON_DOTS = (                                   # <ellipse class="dshwv-b1"/b2/>
    (352.0, 561.0, 37.5, 26.0),
    (442.0, 646.0, 24.5, 18.0),
)
BALLOON_STROKE = 18.0                              # stroke-width="18"
BALLOON_STROKE_COLOR = (32, 49, 112, 255)          # stroke="#203170"
BALLOON_FILL = (255, 255, 255, 255)                # fill="#FFFFFF"

# .dshwv-text 的位置与尺寸（相对 viewBox 的比例）
TEXT_CENTER = (0.4425, 0.36)
TEXT_AREA = (0.66, 0.64)
TEXT_COLOR = (83, 107, 169, 255)                   # color:#536ba9


def arc_points(x1: float, y1: float, rx: float, ry: float, rotation: float,
               large_arc: int, sweep: int, x2: float, y2: float, steps: int = 96):
    """SVG 椭圆弧 → 折线点（端点参数化 → 中心参数化，规范 F.6.5）。"""
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    numerator = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large_arc == sweep:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / norm))
        result = math.acos(value)
        return -result if (ux * vy - uy * vx) < 0 else result

    theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                  (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    points = []
    for index in range(1, steps + 1):
        theta = theta1 + delta * index / float(steps)
        px = cx + rx * math.cos(theta) * cos_phi - ry * math.sin(theta) * sin_phi
        py = cy + rx * math.cos(theta) * sin_phi + ry * math.sin(theta) * cos_phi
        points.append((px, py))
    return points


def path_points(path: str) -> list[tuple[float, float]]:
    """解析本文件用到的那条 path（只含 M / A / Z）。"""
    tokens = path.replace(",", " ").split()
    points: list[tuple[float, float]] = []
    index = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command == "M":
            current = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            start = current
            points.append(current)
        elif command == "A":
            rx, ry = float(tokens[index]), float(tokens[index + 1])
            rotation = float(tokens[index + 2])
            large_arc, sweep = int(tokens[index + 3]), int(tokens[index + 4])
            end = (float(tokens[index + 5]), float(tokens[index + 6]))
            index += 7
            points.extend(arc_points(current[0], current[1], rx, ry, rotation,
                                     large_arc, sweep, end[0], end[1]))
            current = end
        elif command in ("Z", "z"):
            points.append(start)
    return points


_CACHE: dict = {}


def render_balloon(width: int, supersample: int = 3) -> Image.Image:
    """把原版气泡（path + 两个 ellipse）按给定宽度栅格化成 RGBA。"""
    width = max(24, int(width))
    key = (width, supersample)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    s = max(1, int(supersample))
    scale = width / BALLOON_VIEWBOX[0] * s
    height = int(round(BALLOON_VIEWBOX[1] * scale))
    canvas = Image.new("RGBA", (width * s, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    stroke = max(1.0, BALLOON_STROKE * scale)
    radius = stroke / 2.0

    # bshape：椭圆 + 尾部小弧（同一条 path）
    outline = [(x * scale, y * scale) for x, y in path_points(BALLOON_PATH)]
    if outline:
        # 与 SVG 一致：先铺满填充，再画一条**跨在路径上**的描边（内 9 / 外 9）。
        # 注意不能再把多边形重填一次 —— 那会把描边内侧的一半盖掉，看起来只有一半粗。
        draw.polygon(outline, fill=BALLOON_FILL)
        draw.line(outline + [outline[0]], fill=BALLOON_STROKE_COLOR,
                  width=int(round(stroke)), joint="curve")
        for point in outline:                      # 模拟 stroke-linejoin/linecap="round"
            draw.ellipse((point[0] - radius, point[1] - radius,
                          point[0] + radius, point[1] + radius), fill=BALLOON_STROKE_COLOR)

    # b1 / b2：两个圆点。SVG 的 stroke 跨在椭圆边界上（内 9 / 外 9），
    # Pillow 的 outline 却是从 bbox 向内画，所以 bbox 要按 stroke/2 外扩再画。
    for cx, cy, rx, ry in BALLOON_DOTS:
        grow = stroke / 2.0
        box = ((cx - rx) * scale - grow, (cy - ry) * scale - grow,
               (cx + rx) * scale + grow, (cy + ry) * scale + grow)
        draw.ellipse(box, fill=BALLOON_FILL, outline=BALLOON_STROKE_COLOR, width=int(round(stroke)))

    image = canvas.resize((width, max(1, int(round(BALLOON_VIEWBOX[1] * width / BALLOON_VIEWBOX[0])))),
                          Image.LANCZOS)
    _CACHE[key] = image
    return image


def place_ink_centered(content: Image.Image, width: int, tail: str = "down") -> Image.Image:
    """把内容层按**墨迹包围盒**（真正看得见的像素）居中到椭圆中心。

    为什么不能只按"画布中心"居中：
      · 图片模块自带透明边距，画布中心 ≠ 看得见的中心；
      · 文字的字形上下伸不对称（`textbbox` 的 box[1] 常不为 0），会系统性偏上几个像素；
      · chip 的内边距、折行后的空白也会把视觉重心带偏。
    所以统一在这里按 alpha 包围盒对齐 —— 任何内容、任何路径出来的结果都真正居中。
    超出气泡的部分交给调用方的椭圆裁切/缩放兜底。
    """
    width = max(24, int(width))
    height = int(round(BALLOON_VIEWBOX[1] * width / BALLOON_VIEWBOX[0]))
    center_x, center_y, _area_w, _area_h = text_area(width)
    if str(tail).lower() == "up":
        center_y = height - center_y

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ink = content.getchannel("A").getbbox()
    if not ink or content.width == 0 or content.height == 0:
        return layer
    dx = int(round(center_x - (ink[0] + ink[2]) / 2.0))
    dy = int(round(center_y - (ink[1] + ink[3]) / 2.0))
    # alpha_composite 不接受负偏移：先把越界部分裁掉
    source = (max(0, -dx), max(0, -dy),
              content.width + min(0, dx), content.height + min(0, dy))
    if source[2] <= source[0] or source[3] <= source[1]:
        return layer
    layer.alpha_composite(content.crop(source), (max(0, dx), max(0, dy)))
    return layer


def clip_to_balloon(layer: Image.Image, width: int, tail: str = "down") -> Image.Image:
    """按椭圆内沿裁切内容层（气泡描边内侧），保证内容不会戳出气泡。"""
    mask = inner_mask(width)
    if str(tail).lower() == "up":
        mask = mask.transpose(Image.FLIP_TOP_BOTTOM)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return layer


def inner_mask(width: int, supersample: int = 1) -> Image.Image:
    """椭圆**内沿**的遮罩（L 模式）：内容用它裁切，避免戳出椭圆外面。

    做法：把 path 填成实心遮罩，再按 stroke/2 腐蚀掉一圈（SVG 描边跨在路径上，
    内侧那 stroke/2 会盖住内容）。
    """
    width = max(24, int(width))
    key = ("mask", width, supersample)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    scale = width / BALLOON_VIEWBOX[0]
    height = int(round(BALLOON_VIEWBOX[1] * scale))
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    outline = [(x * scale, y * scale) for x, y in path_points(BALLOON_PATH)]
    if outline:
        draw.polygon(outline, fill=255)
    stroke = max(1, int(round(BALLOON_STROKE * scale)))
    if stroke > 1:
        size = stroke if stroke % 2 else stroke + 1        # MinFilter 要求奇数
        mask = mask.filter(ImageFilter.MinFilter(min(size, 9)))
    _CACHE[key] = mask
    return mask


def text_area(width: int) -> tuple[float, float, float, float]:
    """文字区域的中心与尺寸（按 .dshwv-text 的 44.25%/36%、66%/64% 换算）。"""
    height = BALLOON_VIEWBOX[1] * width / BALLOON_VIEWBOX[0]
    return (TEXT_CENTER[0] * width, TEXT_CENTER[1] * height,
            TEXT_AREA[0] * width, TEXT_AREA[1] * height)
