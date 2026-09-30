# -*- coding: utf-8 -*-
"""图形层：把带 alpha 的 PNG/GIF 压成 tkinter 透明色键图，并绘制气泡。

tkinter 在 Windows 上做"真透明"只有一条稳的路：把整个窗口背景设成一个键色
（`-transparentcolor`），键色像素既透明、**也不吃鼠标**。于是挂件只有鲸鱼本体可点，
其余地方点击直接穿到桌面 —— 这正是 Bongo Cat Mver 的观感。

代价是半透明边缘会和键色混出彩边，所以这里把 alpha 二值化（硬边），再交给 tkinter。
"""
from __future__ import annotations

import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

import whale_colors as colors
import whale_presets as presets
import whale_svg as svg

# 键色：纯品红偏一点，正常素材里不会出现
KEY_HEX = "#ff00fe"
KEY_RGB = (255, 0, 254)

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",   # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
]

# 强调色（¥ 金额那一行）
BUBBLE_ACCENT = (214, 69, 69, 255)


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def flatten(img: Image.Image, key_rgb: tuple[int, int, int] = KEY_RGB, threshold: int = 28) -> Image.Image:
    """把带 alpha 的图压到键色上：alpha < threshold → 键色，其余保留原色（硬边）。

    用「二值化 alpha 当掩膜」交给 Pillow 的 C 实现，不做逐像素循环 ——
    动画每帧都要重画，Python 级循环在 200×200 上就已经跟不上了。
    """
    img = img.convert("RGBA")
    mask = img.getchannel("A").point(lambda a: 255 if a >= threshold else 0)
    out = Image.new("RGB", img.size, key_rgb)
    out.paste(img.convert("RGB"), (0, 0), mask)
    return out


def load_sprite(path: str, scale: float = 1.0, threshold: int = 28) -> Image.Image:
    """读一张 PNG 并按 scale 缩放，返回可直接给 tkinter 的键色图。"""
    img = Image.open(path).convert("RGBA")
    if scale != 1.0:
        size = (max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale))))
        img = img.resize(size, Image.LANCZOS)
    return flatten(img, KEY_RGB, threshold)


def load_gif_frames(path: str, scale: float = 1.0, threshold: int = 28) -> list[Image.Image]:
    """把 GIF 拆成帧（用于"图片台词"气泡）；失败返回空列表。"""
    return [frame for frame, _ms in load_gif_frames_timed(path, scale, threshold)]


def load_gif_frames_timed(path: str, scale: float = 1.0, threshold: int = 28,
                          default_ms: int = 110) -> list[tuple[Image.Image, int]]:
    """把 GIF 拆成 (帧, 该帧时长ms) —— 时长取 GIF 自带值，缺省用 default_ms。

    浏览器里的 <img> 会按 GIF 自带的每帧延迟播放；Python 侧要自己排期，
    所以把时长一起带出来，播放速度倍率在此基础上乘。
    """
    frames: list[tuple[Image.Image, int]] = []
    try:
        img = Image.open(path)
    except Exception:
        return frames
    try:
        while True:
            try:
                duration = int(img.info.get("duration") or default_ms)
            except (TypeError, ValueError):
                duration = default_ms
            frame = img.convert("RGBA")
            if scale != 1.0:
                size = (max(1, int(round(frame.width * scale))), max(1, int(round(frame.height * scale))))
                frame = frame.resize(size, Image.LANCZOS)
            frames.append((flatten(frame, KEY_RGB, threshold), max(20, duration)))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    except Exception:
        pass
    return frames


def render_rua_bubble_frames(gif_path: str, target_width: int = 120) -> list[tuple[Image.Image, int]]:
    """把 rua.gif 按气泡宽度缩放成一组 (帧, 时长)（用于"图片台词"气泡）。"""
    if not os.path.isfile(gif_path):
        return []
    try:
        probe = Image.open(gif_path)
        scale = target_width / float(max(1, probe.width))
    except Exception:
        return []
    return load_gif_frames_timed(gif_path, scale=scale)


def key_to_alpha(img: Image.Image, key_rgb: tuple[int, int, int] = KEY_RGB, tolerance: int = 6) -> Image.Image:
    """把键色还原成透明（只用于离屏预览/合成，不参与窗口渲染）。"""
    img = img.convert("RGB")
    diff = ImageChops.difference(img, Image.new("RGB", img.size, key_rgb)).convert("L")
    mask = diff.point(lambda v: 0 if v <= tolerance else 255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def checkerboard(width: int, height: int, cell: int = 16,
                 colors=((58, 58, 62), (74, 74, 80))) -> Image.Image:
    """棋盘底色，用来一眼看出哪些像素是透明的。"""
    board = Image.new("RGB", (width, height), colors[0])
    draw = ImageDraw.Draw(board)
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=colors[1])
    return board.convert("RGBA")


def render_slots(slots: list, width: int, key_rgb: tuple[int, int, int] = KEY_RGB,
                 supersample: int = 3, tail: str = "down", split: bool = False):
    """按原版的**三行结构**渲染气泡内容。

    slots = [label, amount, hint]，每项可为 None 或 {"t":文本, "s":样式A/B/P/C,
    "c":颜色/配色方案名, "w":是否折行}。字号一律按 `--dshw-u = 挂件宽/1026` 换算，
    所以整体随挂件尺寸自动缩放；超出行内可用区域时再整体等比缩小（自动适配）。

    返回 (气泡层, 内容层) 或键色合成图。
    """
    balloon = svg.render_balloon(width, supersample=supersample)
    height = balloon.height
    center_x, center_y, area_w, area_h = svg.text_area(width)
    unit = width / presets.U_BASE

    if tail == "up":
        balloon = balloon.transpose(Image.FLIP_TOP_BOTTOM)
        center_y = height - center_y

    s = supersample
    canvas = Image.new("RGBA", (width * s, height * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # ---- 量一遍：每行的高度与行数（原版 label/amount/hint 依次竖排，hint 多 9u 上边距）----
    rows = []
    for slot in (slots or []):
        if not slot or not str(slot.get("t") or "").strip():
            continue
        letter = str(slot.get("s") or "A").upper()
        style = presets.STYLE_BY_LETTER.get(letter, presets.STYLE_BY_LETTER["A"])
        size_px = max(7.0, style["u"] * unit) * s
        font = find_font(int(round(size_px)))
        wrap_width = presets.WRAP_MAX_WIDTH_U * unit * s if slot.get("w") else None
        line_height = presets.WRAP_LINE_HEIGHT if slot.get("w") else style["line_height"]
        lines = _wrap_text(str(slot["t"]), font, wrap_width)
        block_h = size_px * line_height * len(lines)
        if style.get("min_height_u"):
            block_h = max(block_h, style["min_height_u"] * unit * s)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        widths = [probe.textlength(line, font=font) for line in lines]
        rows.append({"slot": slot, "style": style, "font": font, "size": size_px,
                     "lines": lines, "widths": widths, "line_height": line_height,
                     "block_h": block_h, "gap": style.get("margin_top_u", 0) * unit * s})

    total_h = sum(r["block_h"] + r["gap"] for r in rows)
    max_w = max([max(r["widths"]) for r in rows] + [1.0])
    # 内接矩形内放不下就整体缩小（原版靠字号随挂件缩放；这里再兜一层自适应）
    fit = min(1.0, (area_w * 0.78) / max(1.0, max_w / s), (area_h * 0.78) / max(1.0, total_h / s))

    y = center_y * s - (total_h * fit) / 2.0
    for row in rows:
        row_h = row["block_h"] * fit
        y += row["gap"] * fit
        line_y = y
        for line, line_w in zip(row["lines"], row["widths"]):
            font = row["font"]
            if fit < 0.999:                      # 字号随 fit 一起缩：重画一个更小的字号
                font = find_font(max(6, int(round(row["size"] * fit))))
                line_w = draw.textlength(line, font=font)
            x = center_x * s - line_w / 2.0
            box = draw.textbbox((0, 0), line, font=font)
            color = _row_color(row["slot"], row["style"])
            # 原版 text-shadow: 0 1px 2px rgba(255,255,255,.6)
            draw.text((x - box[0], line_y - box[1] + 1), line, font=font, fill=(255, 255, 255, 150))
            if isinstance(color, tuple):          # 纯色
                draw.text((x - box[0], line_y - box[1]), line, font=font, fill=color)
            else:                                 # 渐变（原版配色方案）
                _draw_gradient_text(canvas, line, font, int(round(x - box[0])), int(round(line_y - box[1])),
                                    color, box)
            line_y += row["size"] * fit * row["line_height"]
        y += row_h

    content = canvas.resize((width, height), Image.LANCZOS)
    # 统一按**墨迹**居中到椭圆中心（字形上下伸不对称也不会偏），再裁进椭圆内沿
    layer = svg.clip_to_balloon(svg.place_ink_centered(content, width, tail), width, tail)
    if split:
        return balloon, layer
    return flatten(Image.alpha_composite(balloon, layer), key_rgb)


def _wrap_text(text: str, font, max_width):
    """按像素宽度折行（max_width=None 时不折）。"""
    if not max_width:
        return [text]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    out, current = [], ""
    for ch in text:
        candidate = current + ch
        if current and probe.textlength(candidate, font=font) > max_width:
            out.append(current)
            current = ch
        else:
            current = candidate
    out.append(current)
    return out


def _row_color(slot: dict, style: dict):
    """行颜色：slot 的 c（纯色 / 配色方案名）> 样式自带色 > 基色 #536ba9。

    配色方案名返回 RGB 停点列表（走渐变），纯色返回 (r,g,b,a)。
    """
    raw = str(slot.get("c") or "").strip()
    scheme = raw.lstrip("#").lower() if raw else ""
    if scheme and scheme in colors.TEXT_GRADIENTS:
        return colors.TEXT_GRADIENTS[scheme]
    if raw.startswith("#") or "," in raw or raw.lower().startswith("rgb"):
        return _parse_color(raw) + (255,)
    named = colors.SOLID_NAMES.get(scheme)
    if named:
        return named + (255,)
    style_color = style.get("color")
    if style_color:
        return colors.SOLID_NAMES.get(style_color, colors.TEXT_BASE) + (255,)
    return colors.TEXT_BASE + (255,)


def _parse_color(value: str):
    text = str(value or "").strip()
    if text.lower().startswith("rgb"):
        try:
            parts = text[text.index("(") + 1:text.index(")")].split(",")
            return tuple(max(0, min(255, int(float(p)))) for p in parts[:3])
        except Exception:
            return colors.TEXT_BASE
    body = text.lstrip("#")
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    try:
        return tuple(int(body[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return colors.TEXT_BASE


def _draw_gradient_text(canvas, text, font, x, y, stops, box):
    """原版配色方案是 90deg 的 linear-gradient：横向铺一条渐变，用字形当遮罩。

    遮罩与渐变共用同一个原点（字体度量高度），字形不会被裁。
    """
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    width = max(1, int(round(probe.textlength(text, font=font))))
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = font.size, int(font.size * 0.25)
    height = max(1, int(ascent + descent))
    gradient = Image.new("RGB", (width, height))
    pixels = gradient.load()
    count = max(1, len(stops) - 1)
    for px in range(width):
        pos = px / float(max(1, width - 1)) * count
        index = min(count - 1, int(pos))
        ratio = pos - index
        a, b = stops[index], stops[min(index + 1, len(stops) - 1)]
        pixels_row = tuple(int(round(a[i] + (b[i] - a[i]) * ratio)) for i in range(3))
        for py in range(height):
            pixels[px, py] = pixels_row
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(gradient, (0, 0), mask)
    canvas.alpha_composite(layer, (int(x), int(y)))


def render_bubble(lines: list, width: int, key_rgb: tuple[int, int, int] = KEY_RGB,
                  accent: bool = False, supersample: int = 3, ui_scale: float = 1.0,
                  tail: str = "down", split: bool = False):
    """兼容入口：把"若干行文字"转成原版的三行结构再渲染。

    · 传字符串列表 → 逐行当作 A 样式（label 样式）居中排；
    · 传 [label, amount, hint] 这种槽位（元素可为 None / dict）→ 直接走 render_slots。
    新代码请直接用 render_slots()，样式/颜色/缩放规则都在那边（抄自原版）。
    """
    if isinstance(lines, dict):
        slots = [lines]                                   # 直接给一个槽位
    elif isinstance(lines, (list, tuple)):
        if lines and all(isinstance(item, (dict, type(None))) for item in lines):
            slots = list(lines)                           # 三行结构 [label, amount, hint]
        else:
            slots = [{"t": str(item), "s": "A"} for item in lines if str(item).strip()]
            if accent and slots:                          # ¥/$ 开头的行用强调色
                slots[0]["c"] = "#d64545"
    else:
        slots = []
    return render_slots(slots, width, key_rgb=key_rgb, supersample=supersample,
                        tail=tail, split=split)
