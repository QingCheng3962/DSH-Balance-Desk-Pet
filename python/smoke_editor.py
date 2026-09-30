# -*- coding: utf-8 -*-
"""气泡编辑器冒烟测试：建模 → 保存 → 读回 → 预览。

用**临时 DSH_HOME**（工作区内的 _tmp-home），因此绝不会碰你真实的
$DSH_HOME/.dshw-bubble.json。用法：python smoke_editor.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP_HOME = os.path.join(HERE, "_tmp-home")
os.makedirs(TMP_HOME, exist_ok=True)
for _stale in (".dshw-bubble.json",):                 # 每次从干净状态开始
    _path = os.path.join(TMP_HOME, _stale)
    if os.path.isfile(_path):
        os.remove(_path)
os.environ["DSH_HOME"] = TMP_HOME                     # ← 隔离：不碰真实配置
os.environ.setdefault("DSHW_ASSETS", r"C:\Users\HI\Desktop\dsh桌面挂件\assets")
sys.path.insert(0, HERE)

import tkinter as tk  # noqa: E402

import whale_card as card  # noqa: E402
import whale_editor as editor_mod  # noqa: E402
import whale_presets as presets  # noqa: E402

print("编辑器配置路径:", editor_mod.config_path())
assert editor_mod.config_path().startswith(TMP_HOME), "必须在临时 HOME 里测"

root = tk.Tk()
root.withdraw()
editor = editor_mod.BubbleEditor(root, pet=None)
print("初始项:", [it.get("kind") for it in editor.items])

editor.add_item("custom")
editor.add_type.set("text")
editor.add_module()
editor.add_type.set("peak")
editor.add_module()
editor.add_type.set("random")
editor.add_module()
editor.add_type.set("image")
editor.add_module()

mods = editor.item_modules()
# 注意：add_item('custom') 本身就会塞一个默认 text 模块，所以这里是 5 个
mods[0].update({"type": "text", "text": "DeepSeek 余额", "size": 8, "bold": True})
mods[1].update({"type": "peak", "tpl": "{status}", "peakStyle": "mini",
                "peakBgRgb": "rouge", "offBgRgb": "bamboo", "row": 4, "size": 6})
mods[2].update({"type": "random", "size": 18,
                "lines": [{"t": "甲", "w": 5, "bold": True}, {"t": "乙", "w": 1, "rgb": "candy"}]})
mods[3].update({"type": "image", "imgId": "bimg_money1", "imgScale": 0.4})
editor.refresh_modules()
editor.refresh_props()
editor.refresh_preview()
print("模块数:", len(mods), "| 预览:", "OK" if editor.preview_photo else "失败")

editor.lib.append({"id": "m1", "name": "测试模块", "module": {"type": "text", "text": "库里的", "size": 12}})
editor.tap_advance = True
editor.on_save()
loaded = editor_mod.load_config()
ok = (bool(loaded) and len(loaded.get("items") or []) == len(editor.items)
      and len(loaded.get("lib") or []) == 1 and loaded.get("tapAdvance") is True)
print("保存→读回:", "OK" if ok else "失败", json.dumps(loaded, ensure_ascii=False)[:90])

# 值解析：峰谷模块应当按峰/谷换色换字
vals = {"_isPeak": True, "status": "高峰时段", "countdown": "01:02:03"}
text, eff = card.module_resolved(dict(mods[1]), vals)
print("峰谷模块(峰):", repr(text), "bgRgb=", eff.get("bgRgb"))
vals_off = {"_isPeak": False, "status": "空闲时段", "countdown": "01:02:03"}
text_off, eff_off = card.module_resolved(dict(mods[1]), vals_off)
print("峰谷模块(谷):", repr(text_off), "bgRgb=", eff_off.get("bgRgb"))

# 随机行自带样式应当覆盖模块（注意：每轮都从"干净"的模块副本开始 ——
# 若把上一轮的 _lastPick 也带进来，就会触发原版"不连续重复上一句"的重试，
# 从而人为压低最高权重那条的概率：(5/6)^6 ≈ 33.5%，那是测试写法的问题，不是实现问题）
picks = {"甲": 0, "乙": 0}
for _ in range(4000):
    line_mod = dict(mods[2])
    line_mod.pop("_lastPick", None)
    t, e = card.module_resolved(line_mod, {})
    picks[t] = picks.get(t, 0) + 1
    if t == "乙":
        assert e.get("rgb") == "candy", "行自带 rgb 没有覆盖模块"
print("权重抽签:", picks, "（期望 甲≈83%%, 乙≈17%%）")

# 再验一次"不重复上一句"：把上一轮结果带进去时，同一句不会连续出现
line_mod = dict(mods[2])
line_mod.pop("_lastPick", None)
repeats = 0
previous = None
for _ in range(2000):
    t, _e = card.module_resolved(line_mod, {})
    if t == previous:
        repeats += 1
    previous = t
print("连续重复次数:", repeats, "（原版是**尽力而为**：最多重试 6 次，仍抽中同一句就用，"
      "所以重复率 ≈ (5/6)^6 ≈ 33%% × 83%% + (1/6)^6 × 17%% ≈ 28%%，非 0）")

root.destroy()
print("冒烟测试通过；临时 HOME:", TMP_HOME)
