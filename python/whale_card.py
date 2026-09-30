# -*- coding: utf-8 -*-
"""卡片渲染：按 DSH 原版前端（whale-widget.js）的模块结构绘制提醒卡片。

原版的提醒内容是"模块数组"，每个模块一行或并列一行：

    {type:'text',  text:'上一轮对话消耗:', size:8, bold:true}
    {type:'text',  text:'¥ {cost}',      size:24, bold:true, color:'#e0433f'}
    {type:'today', tpl:'今日已用 {expense_ds}', size:2, bgRgb:'indigo', color:'#fff'}
    {type:'image', imgId:'bimg_money1',  imgScale:0.4}
    {type:'link',  text:'>> 喂 点 米 <<', url:'https://…', color:'#fff', bgRgb:'indigo'}

这里把同一套结构画成 Pillow 图，关键规则与原版对齐：

* 字号：``min(40, round(12 + (n-1)*0.8))``（原版 ``usageLineFontPx``）
* 文本模块：居中小块，``margin: 4px auto``，行高 1.4，bold → 700
* 底色模块：圆角 7px + 左右 8px 内边距（`bg` / `bgRgb`）
* 图片模块：``maxWidth = 240 * clamp(imgScale, 0.1, 1)``，maxHeight 120px
* 同一 ``row`` 的模块并排一行
"""
from __future__ import annotations

import os

from PIL import Image, ImageChops, ImageDraw

from whale_bubble import KEY_RGB, find_font, flatten

import whale_colors as colors
import whale_presets as presets
import whale_svg as svg

# 原版主色
INDIGO = "#203170"
ROUGE = "#c0392b"
CARD_BG = (255, 255, 255, 251)
CARD_BORDER = (208, 215, 228, 255)
CARD_TEXT = (32, 49, 112, 255)

NAMED_COLORS = {
    "indigo": INDIGO,
    "rouge": ROUGE,
    "white": "#ffffff",
    "black": "#000000",
    "red": "#e0433f",
    "gray": "#8a93a6",
}

# 内置泡泡图 id → assets 文件名（原版 bubble-money1.gif 是余额预警的配图）
BUILTIN_IMAGES = {
    "bimg_money1": "bubble-money1.gif",
    "bimg_petpet": "bubble-petpet.gif",
    "bimg_rua": "rua.gif",
}


def line_font_px(level, ui_scale: float = 1.0) -> float:
    """原版 ``usageLineFontPx``：字号档位 → 像素。"""
    try:
        n = int(round(float(level)))
    except (TypeError, ValueError):
        n = 7
    n = max(1, min(50, n))
    return min(40.0, float(round(12 + (n - 1) * 0.8))) * ui_scale


def parse_color(value, default=(32, 49, 112)) -> tuple[int, int, int]:
    """颜色名 / #rrggbb / rgb() 都吃。"""
    if not value:
        return default
    text = str(value).strip()
    named = NAMED_COLORS.get(text.lower())
    if named:
        text = named
    if text.startswith("#"):
        body = text[1:]
        if len(body) == 3:
            body = "".join(ch * 2 for ch in body)
        try:
            return tuple(int(body[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            return default
    if text.lower().startswith("rgb("):
        try:
            parts = text[text.index("(") + 1:text.index(")")].split(",")
            return tuple(max(0, min(255, int(float(p)))) for p in parts[:3])  # type: ignore[return-value]
        except Exception:
            return default
    return default


def fill_text(text: str, values: dict | None) -> str:
    """占位替换：{below} / {amount} / {cost} / {session} / {expense_ds}。"""
    values = values or {}
    out = str(text or "")
    for key, value in values.items():
        out = out.replace("{%s}" % key, "" if value is None else str(value))
    return out


def _content_bounds(img: Image.Image) -> tuple[int, int, int, int] | None:
    try:
        return img.getchannel("A").getbbox()
    except Exception:
        return None


_IMAGE_CACHE: dict = {}


def load_module_image(path: str) -> Image.Image | None:
    """读一个图片模块。

    动图（如 bubble-money1.gif，500×399 / 86 帧）第 0 帧往往几乎空白，
    所以采样若干帧取**并集包围盒**，并取中间帧作为静态显示 —— 这样卡片上的
    内容既完整又居中。结果按路径缓存（卡片可能被反复渲染）。
    """
    if path in _IMAGE_CACHE:
        return _IMAGE_CACHE[path]
    try:
        source = Image.open(path)
    except Exception:
        return None

    frames: list[Image.Image] = []
    try:
        total = int(getattr(source, "n_frames", 1) or 1)
        step = max(1, total // 12)
        for index in range(0, max(1, total), step):
            source.seek(index)
            frames.append(source.convert("RGBA"))
        source.seek(0)
    except Exception:
        frames = []
    if not frames:
        try:
            frames = [source.convert("RGBA")]
        except Exception:
            return None

    union = None
    for frame in frames:
        box = _content_bounds(frame)
        if not box:
            continue
        union = box if union is None else (min(union[0], box[0]), min(union[1], box[1]),
                                           max(union[2], box[2]), max(union[3], box[3]))
    result = frames[len(frames) // 2]
    if union:
        result = result.crop(union)
    # 大面积纯白（调色板动图常见）就再按不透明像素收紧一次
    box = _content_bounds(result)
    if box:
        result = result.crop(box)
    _IMAGE_CACHE[path] = result
    return result


def resolve_image(img_id: str, assets: str) -> str | None:
    """把模块里的 imgId 解析成 assets 下的文件路径。"""
    if not img_id:
        return None
    if os.path.isabs(img_id) and os.path.isfile(img_id):
        return img_id
    name = BUILTIN_IMAGES.get(str(img_id), str(img_id))
    for candidate in (name, name + ".gif", name + ".png"):
        path = os.path.join(assets, candidate)
        if os.path.isfile(path):
            return path
    # 兜底：按 id 片段找同名文件
    try:
        for entry in os.listdir(assets):
            if str(img_id) in entry and entry.lower().endswith((".gif", ".png")):
                return os.path.join(assets, entry)
    except Exception:
        pass
    return None


def _group_rows(modules: list[dict]) -> list[list[dict]]:
    """按原版 ``row`` 语义分组：同一 row 的相邻模块并排。"""
    rows: list[list[dict]] = []
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        row = mod.get("row")
        if row and rows and rows[-1][0].get("row") == row:
            rows[-1].append(mod)
        else:
            rows.append([mod])
    return rows


def render_bubble_modules(modules: list[dict], assets: str, width: int,
                          values: dict | None = None, tail: str = "down",
                          key_rgb=KEY_RGB, supersample: int = 3, split: bool = False,
                          image_dirs: list | None = None):
    """渲染**自定义泡泡的模块列表**（原版编辑器里的 modules[]），装进原版气泡里。

    与 render_card 的区别：排版与字号走**泡泡模块的规则**而不是提醒卡片的规则 ——

      · 字号 = bubbleModuleFontU(size 1..50) × u，u = 挂件宽/1026（原版 bubbleModuleFontU）
      · `row` 相同的相邻模块并排一行；图片模块独占一行（原版 bubbleRowsOf）
      · 颜色：`rgb` = 原版配色方案（渐变）；`color` = 纯色；`bg`/`bgRgb` = 底色块
      · `type:'random'` 的 lines[{t,w}] 按权重抽一条（原版 bubblePickLine）
      · `imgId` 先查内置再查用户的 whale-bubble-imgs 图库
    """
    unit = width / presets.U_BASE
    s = max(1, int(supersample))
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    values = values or {}

    # ---- 1) 分组（原版 bubbleRowsOf：图片独占一行，其余按 row 键相邻合并）----
    rows: list[list[dict]] = []
    last_key = None
    for mod in (modules or []):
        if not isinstance(mod, dict):
            continue
        kind = str(mod.get("type") or "text")
        if kind in ("image", "randimg") or mod.get("imgId"):
            rows.append([mod])
            last_key = None
            continue
        key = mod.get("row")
        if rows and key is not None and key == last_key:
            rows[-1].append(mod)
        else:
            rows.append([mod])
            last_key = key

    # ---- 2) 量尺寸 ----
    plan = []
    for row in rows:
        items = []
        row_w = row_h = 0
        for mod in row:
            kind = str(mod.get("type") or "text")
            if kind in ("image", "randimg") or mod.get("imgId"):
                path = resolve_module_image(mod, assets, image_dirs)
                img = load_module_image(path) if path else None
                if img is None:
                    continue
                scale = mod.get("imgScale")
                try:
                    scale = float(scale)
                except (TypeError, ValueError):
                    scale = 1.0
                scale = max(0.1, min(1.0, scale))
                target_w = max(24, int(round(presets.WRAP_MAX_WIDTH_U * unit * scale))) * s
                max_h = int(round(presets.WRAP_MAX_WIDTH_U * unit * 0.55)) * s
                if img.width > target_w:
                    ratio = target_w / float(img.width)
                    img = img.resize((target_w, max(1, int(round(img.height * ratio)))), Image.LANCZOS)
                if img.height > max_h:
                    ratio = max_h / float(img.height)
                    img = img.resize((max(1, int(round(img.width * ratio))), max_h), Image.LANCZOS)
                items.append({"kind": "image", "image": img, "w": img.width, "h": img.height})
                row_w += img.width
                row_h = max(row_h, img.height)
                continue
            text, effective = module_resolved(mod, values)
            if not text:
                continue
            size_px = max(6.0, presets.bubble_module_font_px(effective.get("size"), unit)) * s
            font = find_module_font(size_px, effective)
            wrap_w = presets.WRAP_MAX_WIDTH_U * unit * s if effective.get("w") else None
            lines = _wrap_to(text, font, wrap_w)
            widths = [probe.textlength(line, font=font) for line in lines]
            line_h = size_px * presets.paragraph_line_height_u()
            bg = effective.get("bg") or effective.get("bgRgb") or ""
            chip_pad_h = int(round(8 * unit * s))
            chip_pad_v = int(round(3 * unit * s))
            item_w = max(widths) + (chip_pad_h * 2 if bg else 0)
            item_h = line_h * len(lines) + (chip_pad_v * 2 if bg else 0)
            items.append({"kind": "text", "lines": lines, "widths": widths, "font": font,
                          "w": item_w, "h": item_h, "line_h": line_h, "size_px": size_px,
                          "chip": bool(bg), "bg": parse_color(bg, (32, 49, 112)) if bg else None,
                          "color": module_color(effective), "mod": effective,
                          "pad_h": chip_pad_h, "pad_v": chip_pad_v})
            row_w += item_w
            row_h = max(row_h, item_h)
        if items:
            plan.append((row_h, items, row_w))

    if not plan:
        plan = [(int(20 * unit) * s, [], 0)]

    content_w_px = max(1, max(row[2] for row in plan)) / float(s)
    content_h_px = (sum(row[0] for row in plan) + int(round(6 * unit)) * s * max(0, len(plan) - 1)) / float(s)

    # ---- 3) 内容层 ----
    canvas = Image.new("RGBA", (max(1, int(content_w_px * s)), max(1, int(content_h_px * s))), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    y = 0
    gap = max(2, int(round(6 * unit)) * s)
    for row_h, items, row_w in plan:
        x = max(0, (canvas.width - row_w) // 2)
        for item in items:
            if item["kind"] == "image":
                canvas.alpha_composite(item["image"], (int(x), int(y + (row_h - item["h"]) // 2)))
            else:
                top = y + (row_h - item["h"]) // 2
                if item["chip"]:
                    draw.rounded_rectangle((x, top, x + item["w"] - 1, top + item["h"] - 1),
                                           radius=max(2, int(round(7 * unit)) * s), fill=item["bg"])
                line_y = top + item["pad_v"]
                for line, line_w in zip(item["lines"], item["widths"]):
                    box = probe.textbbox((0, 0), line, font=item["font"])
                    tx = x + item["pad_h"] + (max(item["widths"]) - line_w) / 2.0 - box[0]
                    ty = line_y - box[1]
                    color = item["color"]
                    if isinstance(color, list):
                        _gradient_text(canvas, line, item["font"], tx, ty, color, box)
                    else:
                        draw.text((tx, ty + 1), line, font=item["font"], fill=(255, 255, 255, 150))
                        draw.text((tx, ty), line, font=item["font"], fill=color)
                        if item["mod"].get("ul"):        # 下划线
                            under = line_y + item["size_px"] * 0.98
                            draw.line((tx - box[0], under, tx - box[0] + line_w, under),
                                      fill=color, width=max(1, s // 2))
                    line_y += item["line_h"]
            x += item["w"] + gap
        y += row_h + gap

    content = canvas.resize((max(1, int(content_w_px)), max(1, int(content_h_px))), Image.LANCZOS)
    balloon = svg.render_balloon(width, supersample=s)
    height = balloon.height
    center_x, center_y, area_w, area_h = svg.text_area(width)
    fit = min(1.0, (area_w * 0.78) / max(1, content.width), (area_h * 0.78) / max(1, content.height))
    if fit < 1.0:
        content = content.resize((max(1, int(round(content.width * fit))),
                                  max(1, int(round(content.height * fit)))), Image.LANCZOS)
    if str(tail).lower() == "up":
        balloon = balloon.transpose(Image.FLIP_TOP_BOTTOM)
    # 统一按**墨迹**居中到椭圆中心（图片透明边距、chip 内边距都不会再带偏视觉重心）
    layer = svg.clip_to_balloon(svg.place_ink_centered(content, width, tail), width, tail)
    if split:
        return balloon, layer
    return flatten(Image.alpha_composite(balloon, layer), key_rgb)


def peak_text(mod: dict, is_peak: bool, countdown: str) -> str:
    """峰谷模块的状态文字（原版 bubblePeakText + 倒计时样式）。"""
    style = str(mod.get("peakStyle") or "default")
    if style == "count":
        return countdown
    if style == "liangwen":
        return "梁文峰" if is_peak else "梁文谷"
    if style == "qiangqiang":
        return "!?峰峰?!" if is_peak else "!?谷谷?!"
    if style == "mini":
        return "峰" if is_peak else "谷"
    return "高峰时段" if is_peak else "空闲时段"


def module_resolved(mod: dict, values: dict):
    """把模块解析成 (文本, 合并后的属性)。

    · `random`：按权重抽一行，**该行自带的 bold/size/rgb/color/... 覆盖模块属性**（原版如此）
    · `peak`：按当前峰/谷切换 peakColor/offColor、peakRgb/offRgb、peakBgRgb/offBgRgb，
      文字取 `{status}`（或 count 样式的倒计时），`tpl` 里同时可写 {status}/{countdown}
    """
    kind = str(mod.get("type") or "text")
    merged = dict(mod)
    if kind == "random":
        lines = mod.get("lines")
        if isinstance(lines, list) and lines:
            index = presets.pick_line(lines, mod.get("_lastPick"))
            if index is not None:
                try:
                    mod["_lastPick"] = index
                except Exception:
                    pass
                entry = lines[index] or {}
                merged.update({k: v for k, v in entry.items() if k not in ("t", "w")})
                return str(entry.get("t") or ""), merged
        return "", merged
    if kind in ("peak", "nextpeak"):
        is_peak = bool(values.get("_isPeak"))
        for out_key, peak_key, off_key in (("color", "peakColor", "offColor"),
                                           ("rgb", "peakRgb", "offRgb"),
                                           ("bgRgb", "peakBgRgb", "offBgRgb"),
                                           ("bg", "peakBg", "offBg")):
            value = mod.get(peak_key if is_peak else off_key)
            if value:
                merged[out_key] = value
            else:
                merged.pop(out_key, None)
        status = peak_text(mod, is_peak, str(values.get("countdown") or ""))
        template = str(mod.get("tpl") or "")
        if template:
            return fill_text(template, dict(values, status=status, countdown=status
                                            if str(mod.get("peakStyle")) == "count" else values.get("countdown"))), merged
        return status, merged
    if kind in ("balance", "today", "session"):
        return fill_text(mod.get("tpl"), values), merged
    return str(mod.get("text") or ""), merged


def find_module_font(size_px: float, mod: dict):
    """按 bold 选字体（原版 .dshwv-trow 的 font-weight）。"""
    size = max(6, int(round(size_px)))
    if mod.get("bold"):
        for path in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"):
            if os.path.isfile(path):
                try:
                    from PIL import ImageFont
                    return ImageFont.truetype(path, size)
                except Exception:
                    break
    return find_font(size)


def module_text(mod: dict, values: dict) -> str:
    """模块文本：占位符替换 + random 类型的按权重抽签（原版 bubbleModuleText）。"""
    kind = str(mod.get("type") or "text")
    if kind == "random" and isinstance(mod.get("lines"), list) and mod["lines"]:
        index = presets.pick_line(mod["lines"], mod.get("_lastPick"))
        try:
            mod["_lastPick"] = index
        except Exception:
            pass
        entry = mod["lines"][index] if index is not None else None
        return str((entry or {}).get("t") or "")
    return fill_text(mod.get("tpl") if kind in ("balance", "today", "peak", "session") else mod.get("text"),
                     values)


def module_color(mod: dict):
    """模块颜色：`rgb` 配色方案→渐变停点列表；`color` 纯色；都没有→基色。"""
    scheme = str(mod.get("rgb") or "").strip().lower()
    if scheme and scheme in colors.TEXT_GRADIENTS:
        return colors.TEXT_GRADIENTS[scheme]
    raw = str(mod.get("color") or "").strip()
    if raw:
        return parse_color(raw, colors.TEXT_BASE) + (255,)
    return colors.TEXT_BASE + (255,)


def resolve_module_image(mod: dict, assets: str, extra_dirs: list | None = None):
    """图片模块取图：先内置，再用户的 whale-bubble-imgs 图库。"""
    img_id = str(mod.get("imgId") or mod.get("path") or "")
    path = resolve_image(img_id, assets)
    if path:
        return path
    for directory in (extra_dirs or []):
        if not directory or not os.path.isdir(directory):
            continue
        for entry in os.listdir(directory):
            if img_id and img_id in entry and entry.lower().endswith((".gif", ".png", ".jpg", ".jpeg")):
                return os.path.join(directory, entry)
    return None


def _wrap_to(text: str, font, max_width):
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


def _gradient_text(canvas, text, font, x, y, stops, box):
    """原版配色方案 = 90deg 渐变：横向铺一条渐变，用字形当遮罩。

    遮罩与渐变**共用同一个原点**（字体度量高度），所以字形不会被裁；
    (x, y) 与 draw.text 的原点约定一致。
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
        row = tuple(int(round(a[i] + (b[i] - a[i]) * ratio)) for i in range(3))
        for py in range(height):
            pixels[px, py] = row
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(gradient, (0, 0), mask)
    canvas.alpha_composite(layer, (int(x), int(y)))


def render_card(modules: list[dict], assets: str, values: dict | None = None,
                ui_scale: float = 1.0, width: int = 340, tail: str = "down",
                key_rgb=KEY_RGB, supersample: int = 3, split: bool = False):
    """渲染一张卡片，装进**原版气泡**（原始 SVG path + 两个 ellipse）里。

    ``width``  气泡宽度（原版里 = 挂件宽度；这里由挂件传入）
    ``split=True`` 返回 ``(气泡层 RGBA, 内容层 RGBA, links)``
    """
    s = supersample
    pad = max(6, int(round(14 * ui_scale))) * s
    row_gap = max(2, int(round(6 * ui_scale))) * s
    tail_w = max(8, int(round(22 * ui_scale))) * s
    tail_h = max(5, int(round(10 * ui_scale))) * s
    radius = max(5, int(round(14 * ui_scale))) * s
    stroke = max(1, int(round(1.2 * ui_scale * s)))
    chip_pad_x = max(3, int(round(8 * ui_scale))) * s
    chip_pad_y = max(1, int(round(3 * ui_scale))) * s
    # 排版宽度上限 = 原版文字区的宽度（超出的部分后面再等比缩放回文字区）
    _area = svg.text_area(width)
    limit = max(60, int(round(_area[2])) * s)

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rows = _group_rows(modules or [])
    if not rows:
        rows = [[{"type": "text", "text": "", "size": 4}]]

    # ---- 先量一遍每行的尺寸与元素 ----
    plan = []           # [(row_height, [item...])]
    for row in rows:
        items = []
        row_h = 0
        row_w = 0
        for mod in row:
            kind = str(mod.get("type") or "text")
            if kind in ("image", "img", "randimg"):
                path = resolve_image(mod.get("imgId") or mod.get("path") or "", assets)
                if not path:
                    continue
                scale = mod.get("imgScale")
                try:
                    scale = float(scale)
                except (TypeError, ValueError):
                    scale = 1.0
                scale = max(0.1, min(1.0, scale))
                target_w = max(24, int(round(240 * scale * ui_scale))) * s
                max_h = int(round(120 * ui_scale)) * s
                try:
                    img = load_module_image(path)
                except Exception:
                    img = None
                if img is None:
                    continue
                if img.width > target_w:
                    ratio = target_w / float(img.width)
                    img = img.resize((target_w, max(1, int(round(img.height * ratio)))), Image.LANCZOS)
                if img.height > max_h:
                    ratio = max_h / float(img.height)
                    img = img.resize((max(1, int(round(img.width * ratio))), max_h), Image.LANCZOS)
                items.append({"kind": "image", "image": img, "w": img.width, "h": img.height})
                row_w += img.width
                row_h = max(row_h, img.height)
                continue

            text = fill_text(mod.get("tpl") if kind == "today" else mod.get("text"), values)
            font_px = max(7, int(round(line_font_px(mod.get("size"), ui_scale))) * s)
            font = find_font(font_px)
            if not text:
                items.append({"kind": "space", "w": 0, "h": font_px // 2})
                row_h = max(row_h, font_px // 2)
                continue
            box = measure.textbbox((0, 0), text, font=font)
            text_w = box[2] - box[0]
            text_h = box[3] - box[1]
            bg = mod.get("bg") or mod.get("bgRgb") or ""
            chip = bool(bg)
            item_w = text_w + (chip_pad_x * 2 if chip else 0)
            item_h = text_h + (chip_pad_y * 2 if chip else 0)
            items.append({
                "kind": "link" if kind == "link" else "text",
                "text": text, "font": font, "w": item_w, "h": max(item_h, int(font_px * 1.4)),
                "text_w": text_w, "text_h": text_h, "chip": chip,
                "bg": parse_color(bg, (32, 49, 112)) if chip else None,
                "color": parse_color(mod.get("color"), (255, 255, 255) if chip else (32, 49, 112)),
                "bold": bool(mod.get("bold")),
                "url": mod.get("url") if kind == "link" else None,
                "no_wrap": bool(mod.get("noWrap")),
            })
            row_w += item_w + (int(round(6 * ui_scale)) * s if len(row) > 1 else 0)
            row_h = max(row_h, item_h)
        if items:
            plan.append((row_h, items, row_w))

    if not plan:
        plan = [(int(20 * ui_scale) * s, [{"kind": "space", "w": 0, "h": int(20 * ui_scale) * s}], 0)]

    content_w_px = min(limit, max(row[2] for row in plan)) / float(s)
    content_h_px = (sum(row[0] for row in plan) + row_gap * max(0, len(plan) - 1)) / float(s)

    # ---- 1) 内容先画在自己的画布上（超采样，再缩到 1×）----
    canvas = Image.new("RGBA", (max(1, int(round(content_w_px * s))),
                                max(1, int(round(content_h_px * s)))), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    links: list[dict] = []
    y = 0
    for row_h, items, row_w in plan:
        x = (canvas.width - min(row_w, canvas.width)) // 2
        for item in items:
            if item["kind"] == "image":
                canvas.alpha_composite(item["image"], (int(x), int(y + (row_h - item["h"]) // 2)))
            elif item["kind"] == "space":
                pass
            else:
                item_h = item["h"]
                top = y + (row_h - item_h) // 2
                if item["chip"]:
                    draw.rounded_rectangle(
                        (x, top, x + item["w"] - 1, top + item_h - 1),
                        radius=max(3, int(round(7 * ui_scale)) * s), fill=item["bg"],
                    )
                tx = x + (chip_pad_x if item["chip"] else 0)
                ty = top + (chip_pad_y if item["chip"] else 0)
                box = measure.textbbox((0, 0), item["text"], font=item["font"])
                draw.text((tx - box[0], ty - box[1]), item["text"], font=item["font"], fill=item["color"],
                          stroke_width=(max(1, s // 3) if item["bold"] else 0), stroke_fill=item["color"])
                if item.get("url"):
                    links.append({"url": item["url"], "rect": (int(x), int(top), int(item["w"]), int(item_h))})
            x += item["w"] + (int(round(6 * ui_scale)) * s if len(items) > 1 else 0)
        y += row_h + row_gap

    content = canvas.resize((max(1, int(round(content_w_px))), max(1, int(round(content_h_px)))),
                            Image.LANCZOS)

    # ---- 2) 原版气泡（宽度由挂件宽度决定），内容等比缩放后放进原版文字区 ----
    balloon = svg.render_balloon(width, supersample=s)
    height = balloon.height
    center_x, center_y, area_w, area_h = svg.text_area(width)
    # 内容按**内接矩形**（0.78 倍文字区）缩放，再从椭圆内沿裁切兜底，
    # 这样卡片再高也不会把字切掉或戳出描边。
    fit = min(1.0, (area_w * 0.78) / max(1, content.width),
              (area_h * 0.78) / max(1, content.height))
    if fit < 1.0:
        content = content.resize((max(1, int(round(content.width * fit))),
                                  max(1, int(round(content.height * fit)))), Image.LANCZOS)
    if str(tail).lower() == "up":
        balloon = balloon.transpose(Image.FLIP_TOP_BOTTOM)
        center_y = height - center_y

    layer = Image.new("RGBA", balloon.size, (0, 0, 0, 0))
    paste_x = int(round(center_x - content.width / 2.0))
    paste_y = int(round(center_y - content.height / 2.0))
    layer.alpha_composite(content, (paste_x, paste_y))

    # 裁进椭圆内沿：内容再高也不会戳到描边外面
    limit_mask = svg.inner_mask(width)
    if str(tail).lower() == "up":
        limit_mask = limit_mask.transpose(Image.FLIP_TOP_BOTTOM)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), limit_mask))

    links_out = [{"url": link["url"],
                  "rect": (paste_x + int(round(link["rect"][0] * fit)),
                           paste_y + int(round(link["rect"][1] * fit)),
                           max(1, int(round(link["rect"][2] * fit))),
                           max(1, int(round(link["rect"][3] * fit))))}
                 for link in links]
    if split:
        return balloon, layer, links_out
    return flatten(Image.alpha_composite(balloon, layer), key_rgb), links_out
