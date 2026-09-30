# -*- coding: utf-8 -*-
"""从 whale-widget.js 里提取原版的"配色方案"（渐变的 RGB 停点），生成 whale_colors.py。

原版源码里这些是 CSS 条目，形如：

  '.dshwv-trowtx.dshwv-rgb-candy{background-image:linear-gradient(90deg,rgb(255,145,170),…)}'

手抄容易错，所以直接扫源码生成 —— 与 whale_svg.py 一样，属于"抄源码"而非"照着眼睛画"。
用法：python extract_colors.py <whale-widget.js> [输出文件=whale_colors.py]
"""
import io
import re
import sys

SOURCE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\HI\Desktop\dsh桌面挂件\assets\whale-widget.js"
OUT = sys.argv[2] if len(sys.argv) > 2 else "whale_colors.py"
PATTERN = re.compile(
    r"\.dshwv-trowtx\.dshwv-rgb-([a-z0-9]+)\{background-image:linear-gradient\(90deg,(.*?)\)\}",
    re.I,
)
# 不带后缀的那条（'.dshwv-trowtx.dshwv-rgb{...}'）就是编辑器里的「马卡龙」。
# 注意：这里必须贪婪吃到最后一个 ')'（用 [^}]* 而不是 .*?），否则会在第一个 rgb(...) 处截断。
BASE_PATTERN = re.compile(
    r"\.dshwv-trowtx\.dshwv-rgb\{background-image:linear-gradient\(90deg,([^}]*)\)[^}]*\}",
    re.I,
)
STOP = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)


def main() -> None:
    text = open(SOURCE, "r", encoding="utf-8", errors="replace").read()
    schemes: dict[str, list[tuple[int, int, int]]] = {}
    for name, body in PATTERN.findall(text):
        stops = [(int(r), int(g), int(b)) for r, g, b in STOP.findall(body)]
        if stops:
            schemes.setdefault(name.lower(), stops)
    for body in BASE_PATTERN.findall(text):        # 「马卡龙」= 无后缀的那条彩虹渐变
        stops = [(int(r), int(g), int(b)) for r, g, b in STOP.findall(body)]
        if stops:
            schemes.setdefault("macaron", stops)

    out = io.StringIO()
    w = out.write
    w('# -*- coding: utf-8 -*-\n')
    w('"""原版文字配色方案（渐变 RGB 停点）—— 由 extract_colors.py 从 whale-widget.js 生成。\n\n')
    w('不要手改：改原版 CSS 后重新生成即可：\n')
    w('    python extract_colors.py ..\\assets\\whale-widget.js whale_colors.py\n"""\n\n')
    w("TEXT_GRADIENTS: dict = {\n")
    for name in sorted(schemes):
        w("    %r: [\n" % name)
        for stop in schemes[name]:
            w("        %r,\n" % (stop,))
        w("    ],\n")
    w("}\n\n")
    w("# 纯色名（原版 color / bgRgb 里出现的名字）\n")
    w("SOLID_NAMES = {\n")
    w("    'indigo': (32, 49, 112),\n")
    w("    'rouge': (192, 57, 43),\n")
    w("    'ink': (20, 20, 20),\n")
    w("    'muted': (159, 176, 217),   # .dshwv-hint 的 #9fb0d9\n")
    w("    'white': (255, 255, 255),\n")
    w("    'black': (0, 0, 0),\n")
    w("}\n\n")
    w("# .dshwv-text 的基础文字色，也是各行的默认色\n")
    w("TEXT_BASE = (83, 107, 169)      # #536ba9\n")
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(out.getvalue())
    print("wrote %s (%d schemes: %s)" % (OUT, len(schemes), ", ".join(sorted(schemes))))


if __name__ == "__main__":
    main()
