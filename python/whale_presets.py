# -*- coding: utf-8 -*-
"""原版气泡的**台词预设、权重与行样式** —— 逐行抄自 whale-widget.js。

源码（assets/whale-widget.js:11799）：

    var BUBBLE_STYLE_CLASS = { A:'dshwv-label', B:'dshwv-amount', P:'dshwv-period', C:'dshwv-hint' }
    function pickOne(arr) { return arr[Math.floor(Math.random() * arr.length)] }
    function singleCenter(style, text, color, wrap) {
      return [null, { t: text, s: style, c: color || '', w: !!wrap }, null]
    }
    var RANDOM_GROUPS = [
      { w: 7,  lines: ... singleCenter('B', pickOne(['好模型... ↓','好女孩...↓'])) },
      { w: 7,  lines: ... singleCenter('A', pickOne([...6 条...]), '', true) },
      { w: 10, lines: ... ({ gif: true }) },
      { w: 3,  lines: ... singleCenter('A', pickOne([...3 条...]), '', true) },
      { w: 1,  lines: ... singleCenter('B', '哦鲸鲸... ') },
    ]

    // 按权重抽 1 条,avoidIdx 用于"不连续重复上一句"
    function bubblePickLine(lines, avoidIdx) { ... Math.max(1, Number(lines[i].w) || 1) ... }

字号一律走 `--dshw-u`（= 挂件宽 / 1026），所以**字号随挂件尺寸自动缩放**：

    .dshwv-label { font-size: calc(var(--dshw-u) * 66);  font-weight: 600; letter-spacing: .06em }
    .dshwv-amount{ font-size: calc(var(--dshw-u) * 128); font-weight: 800; line-height: 1.05 }
    .dshwv-period{ font-size: calc(var(--dshw-u) * 104); font-weight: 800; line-height: 1.05 }
    .dshwv-hint  { font-size: calc(var(--dshw-u) * 56); color: #9fb0d9; letter-spacing: .02em;
                   margin-top: calc(u*9); min-height: calc(u*64); line-height: 1.15 }
    .dshwv-wrap  { white-space: normal; max-width: calc(var(--dshw-u) * 560); line-height: 1.2 }
    .dshwv-text  { color:#536ba9; line-height:1.15 }
"""
from __future__ import annotations

import random

U_BASE = 1026.0                      # --dshw-u = 挂件宽 / 1026

# BUBBLE_STYLE_CLASS + 各行的 CSS 数值
STYLE_BY_LETTER = {
    "A": {"css": "dshwv-label", "u": 66.0, "weight": 600, "letter_spacing": 0.06, "line_height": 1.15},
    "B": {"css": "dshwv-amount", "u": 128.0, "weight": 800, "letter_spacing": 0.0, "line_height": 1.05},
    "P": {"css": "dshwv-period", "u": 104.0, "weight": 800, "letter_spacing": 0.0, "line_height": 1.05},
    "C": {"css": "dshwv-hint", "u": 56.0, "weight": 400, "letter_spacing": 0.02, "line_height": 1.15,
          "color": "muted", "margin_top_u": 9.0, "min_height_u": 64.0},
}
WRAP_MAX_WIDTH_U = 560.0             # .dshwv-wrap max-width
ROW_MARGIN_U = 2.0                   # .dshwv-text .dshwv-trow{margin: calc(u*2) 0}
WRAP_LINE_HEIGHT = 1.2               # .dshwv-wrap line-height


def pick_one(items):
    """原版 pickOne：等概率取一个。"""
    return items[random.randrange(len(items))] if items else ""


def single_center(style: str, text: str, color: str = "", wrap: bool = False):
    """原版 singleCenter：内容放在**中间那行**（三行结构：label / amount / hint）。"""
    return [None, {"t": text, "s": style, "c": color or "", "w": bool(wrap)}, None]


# ---------------------------------------------------------------------------
# 原版 RANDOM_GROUPS —— 台词、权重、分组逐字照搬
# ---------------------------------------------------------------------------
RANDOM_GROUPS = [
    {"w": 7, "lines": lambda: single_center("B", pick_one(["好模型... ↓", "好女孩...↓"]))},
    {"w": 7, "lines": lambda: single_center("A", pick_one([
        "不知道用户有什么用，先赶走吧~",
        "我...我...我也要挣钱吗？",
        "我去吃饭啦，测完叫我",
        "压力一只蓝色大肥鱼？！",
        "DeepSleep...",
        "坏了...用户彻底怒了！",
    ]), "", True)},
    {"w": 10, "lines": lambda: {"gif": True}},
    {"w": 3, "lines": lambda: single_center("A", pick_one([
        "你目录里的dsh是什么...大烧货吗...?",
        "恭喜你实现token自由！token全跑了！",
        "真当我是便宜货啊...",
    ]), "", True)},
    {"w": 1, "lines": lambda: single_center("B", "哦鲸鲸... ")},
]


def pick_random_lines():
    """原版 pickRandomLines：先按组权重抽一组，再由该组给出内容。"""
    total = sum(max(1, int(g.get("w") or 1)) for g in RANDOM_GROUPS)
    roll = random.random() * total
    for group in RANDOM_GROUPS:
        roll -= max(1, int(group.get("w") or 1))
        if roll < 0:
            return group["lines"]()
    return RANDOM_GROUPS[-1]["lines"]()


def pick_line(lines, avoid_idx=None):
    """原版 bubblePickLine：按权重抽一条，最多重试 6 次避免与上一条重复。"""
    if not isinstance(lines, list) or not lines:
        return None
    if len(lines) == 1:
        return 0
    weights = [max(1, int(entry.get("w") or 1)) for entry in lines]
    total = sum(weights)
    pick = len(lines) - 1
    for _ in range(6):
        roll = random.random() * total
        acc = 0
        for index, weight in enumerate(weights):
            acc += weight
            if roll < acc:
                pick = index
                break
        if pick != avoid_idx:
            break
    return pick


def font_px(style_letter: str, unit: float) -> float:
    """按原版公式把样式字母换成像素字号（unit = 挂件宽 / 1026）。"""
    style = STYLE_BY_LETTER.get(str(style_letter).upper(), STYLE_BY_LETTER["A"])
    return max(6.0, style["u"] * unit)


def bubble_module_font_u(level) -> int:
    """原版 bubbleModuleFontU：模块字号档位 1..50 → u 倍数（1→40u，50→240u）。

        function bubbleModuleFontU(level) {
          var n = Math.max(1, Math.min(50, Math.round(Number(level) || 6)))
          return Math.round(40 + (n - 1) * 200 / 49)
        }
    """
    try:
        n = int(round(float(level)))
    except (TypeError, ValueError):
        n = 6
    n = max(1, min(50, n))
    # JS 的 Math.round 是"四舍五入到更接近的整数"（.5 向上），Python 的 round 是银行家舍入，
    # 所以用 floor(x+0.5) 对齐行为。
    import math
    return int(math.floor(40 + (n - 1) * 200.0 / 49.0 + 0.5))


def bubble_module_font_px(level, unit: float) -> float:
    """模块字号（像素）= bubbleModuleFontU(档位) × u。"""
    return max(6.0, bubble_module_font_u(level) * unit)


def paragraph_line_height_u() -> float:
    """`.dshwv-trow{line-height:1.2}`。"""
    return 1.2
