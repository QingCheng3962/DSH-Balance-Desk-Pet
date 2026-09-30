# -*- coding: utf-8 -*-
"""自定义泡泡编辑器 —— 原版那个编辑器（whale-widget.js 的泡泡面板）的 Python 版。

**读写的是 DSH 同一份配置**：`$DSH_HOME/.dshw-bubble.json`，结构与原版完全一致：

    { "v": 1,
      "items": [ {"kind":"normal"} | {"kind":"random"} | {"kind":"custom","modules":[…]} |
                 {"kind":"choice","options":[{"w":3,"item":{…}}, …]} ],
      "lib":   [ {"id":"m1","name":"模块1","module":{…}} ],
      "tapAdvance": false }

模块字段（原版注释，assets/whale-widget.js:12294）：

    {type:'text'|'balance'|'today'|'peak'|'session'|'image'|'random',
     text?, tpl?, size? 1..50, bold?, italic?, ul?, color?, rgb?, bg?, bgRgb?,
     row?, imgId?, imgScale?, lines?:[{t,w}], len?}

所以：在 Python 挂件里编辑，DSH 网页端的挂件也能看到同一份配置，反之亦然。
"""
from __future__ import annotations

import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import whale_bubble as gfx
import whale_card as card
import whale_colors as colors
import whale_data as data
import whale_presets as presets

BUBBLE_FILE = ".dshw-bubble.json"
MODULE_TYPES = [
    ("text", "文本"), ("balance", "余额"), ("today", "今日已用"),
    ("peak", "峰谷"), ("session", "对话名"), ("image", "图片"), ("random", "随机台词"),
]
DEFAULT_ITEMS = [{"kind": "normal"}, {"kind": "random"}]


# ---------------------------------------------------------------- 配置读写
def config_path() -> str:
    """与原版一致：优先 $DSH_HOME，其次 profiles/web（读取时两个都试）。"""
    return os.path.join(data.dsh_home(), BUBBLE_FILE)


def load_config() -> dict | None:
    for path in (os.path.join(data.dsh_home(), BUBBLE_FILE),
                 os.path.join(data.dsh_home(), "profiles", "web", BUBBLE_FILE)):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
            if isinstance(parsed, dict) and parsed.get("v") == 1:
                return parsed
        except Exception:
            continue
    return None


def save_config(cfg: dict) -> bool:
    """原子写；只保留原版认识的字段（items / lib / tapAdvance）。"""
    body = {"v": 1,
            "items": cfg.get("items") or [],
            "lib": cfg.get("lib") or [],
            "tapAdvance": bool(cfg.get("tapAdvance"))}
    path = config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


# ---------------------------------------------------------------- 编辑器
class BubbleEditor:
    """一个 Toplevel：左边点击序列、中间模块、右边属性、下边实时预览。"""

    def __init__(self, master, pet=None):
        self.pet = pet
        self.assets = pet.assets if pet is not None else _find_assets()
        self.balloon_width = getattr(pet, "balloon_width", 480)
        self.image_dirs = [os.path.join(data.dsh_home(), "whale-bubble-imgs")]

        cfg = load_config() or {}
        raw_items = cfg.get("items")
        self.items = clone(raw_items) if isinstance(raw_items, list) and raw_items else clone(DEFAULT_ITEMS)
        lib = cfg.get("lib")
        self.lib = clone(lib) if isinstance(lib, list) else []
        self.tap_advance = bool(cfg.get("tapAdvance"))

        self.item_index = 0
        self.module_index = 0
        self.dirty = False
        self.preview_photo = None

        self.win = tk.Toplevel(master)
        self.win.title("自定义泡泡编辑器（与 DSH 共用 .dshw-bubble.json）")
        self.win.geometry("1180x760")
        self.win.attributes("-topmost", True)
        self._build()
        self.refresh_all()

    # ---------------- 界面骨架 ----------------
    def _build(self) -> None:
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # 左：点击序列
        left = ttk.Frame(panes, padding=4)
        ttk.Label(left, text="点击序列（点一次鲸鱼走一项）", font=("", 10, "bold")).pack(anchor="w")
        self.item_list = tk.Listbox(left, width=26, height=18, exportselection=False)
        self.item_list.pack(fill="both", expand=True, pady=4)
        self.item_list.bind("<<ListboxSelect>>", self.on_pick_item)
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Button(row, text="加默认余额", width=10, command=lambda: self.add_item("normal")).pack(side="left")
        ttk.Button(row, text="加随机台词", width=10, command=lambda: self.add_item("random")).pack(side="left")
        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=2)
        ttk.Button(row2, text="加自定义", width=10, command=lambda: self.add_item("custom")).pack(side="left")
        ttk.Button(row2, text="加并列步骤", width=10, command=lambda: self.add_item("choice")).pack(side="left")
        row3 = ttk.Frame(left)
        row3.pack(fill="x", pady=2)
        ttk.Button(row3, text="上移", width=7, command=lambda: self.move_item(-1)).pack(side="left")
        ttk.Button(row3, text="下移", width=7, command=lambda: self.move_item(1)).pack(side="left")
        ttk.Button(row3, text="删除", width=7, command=self.delete_item).pack(side="left")
        self.tap_var = tk.BooleanVar(value=self.tap_advance)
        ttk.Checkbutton(left, text="点按角色推进队列（tapAdvance）", variable=self.tap_var,
                        command=self.on_tap_toggle).pack(anchor="w", pady=(6, 0))
        panes.add(left, weight=1)

        # 中：模块列表 + 模块库
        mid = ttk.Frame(panes, padding=4)
        ttk.Label(mid, text="该项的模块（同一 row 的相邻模块并排一行）", font=("", 10, "bold")).pack(anchor="w")
        self.module_list = tk.Listbox(mid, width=30, height=14, exportselection=False)
        self.module_list.pack(fill="both", expand=True, pady=4)
        self.module_list.bind("<<ListboxSelect>>", self.on_pick_module)
        mrow = ttk.Frame(mid)
        mrow.pack(fill="x")
        self.add_type = tk.StringVar(value="text")
        ttk.Combobox(mrow, textvariable=self.add_type, width=8, state="readonly",
                     values=[key for key, _ in MODULE_TYPES]).pack(side="left")
        ttk.Button(mrow, text="加模块", width=7, command=self.add_module).pack(side="left")
        ttk.Button(mrow, text="删除", width=6, command=self.delete_module).pack(side="left")
        mrow2 = ttk.Frame(mid)
        mrow2.pack(fill="x", pady=2)
        ttk.Button(mrow2, text="上移", width=7, command=lambda: self.move_module(-1)).pack(side="left")
        ttk.Button(mrow2, text="下移", width=7, command=lambda: self.move_module(1)).pack(side="left")
        ttk.Button(mrow2, text="存到模块库", width=11, command=self.save_to_lib).pack(side="left")
        ttk.Label(mid, text="模块库（可插入到当前项）", font=("", 9, "bold")).pack(anchor="w", pady=(8, 0))
        self.lib_list = tk.Listbox(mid, width=30, height=6, exportselection=False)
        self.lib_list.pack(fill="x", pady=2)
        lrow = ttk.Frame(mid)
        lrow.pack(fill="x")
        ttk.Button(lrow, text="插入", width=7, command=self.insert_from_lib).pack(side="left")
        ttk.Button(lrow, text="删除", width=7, command=self.delete_lib).pack(side="left")
        panes.add(mid, weight=1)

        # 右：属性
        right = ttk.Frame(panes, padding=4)
        ttk.Label(right, text="模块属性", font=("", 10, "bold")).pack(anchor="w")
        self.props = ttk.Frame(right)
        self.props.pack(fill="both", expand=True)
        self.var_cache: dict[str, tk.Variable] = {}
        self._build_props()
        panes.add(right, weight=2)

        # 下：预览 + 保存
        bottom = ttk.Frame(outer)
        bottom.pack(fill="both", expand=True, pady=(8, 0))
        self.preview = tk.Canvas(bottom, bg="#f0f1f5", height=300, highlightthickness=1)
        self.preview.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(bottom, padding=(8, 0))
        side.pack(side="left", fill="y")
        ttk.Button(side, text="保存（写入 .dshw-bubble.json）", command=self.on_save).pack(fill="x")
        ttk.Button(side, text="重新载入", command=self.on_reload).pack(fill="x", pady=4)
        ttk.Button(side, text="恢复默认序列", command=self.on_reset).pack(fill="x")
        ttk.Button(side, text="导入 JSON…", command=self.on_import).pack(fill="x", pady=4)
        ttk.Button(side, text="导出 JSON…", command=self.on_export).pack(fill="x")
        self.status = ttk.Label(side, text="", wraplength=180, foreground="#555")
        self.status.pack(fill="x", pady=8)

    def _build_props(self) -> None:
        """属性面板：字段与原版模块一致。"""
        rows = [
            ("type", "类型", "combo", [key for key, _ in MODULE_TYPES]),
            ("text", "文本 / 模板", "entry", None),
            ("size", "字号档位 1-50", "entry", None),
            ("bold", "加粗", "check", None),
            ("italic", "斜体", "check", None),
            ("ul", "下划线", "check", None),
            ("rgb", "配色方案（渐变）", "combo", [""] + sorted(colors.TEXT_GRADIENTS)),
            ("color", "纯色 #rrggbb", "entry", None),
            ("bgRgb", "底色方案名", "combo", [""] + sorted(colors.TEXT_GRADIENTS)),
            ("bg", "底色 #rrggbb", "entry", None),
            ("row", "行号（同号并排）", "entry", None),
            ("w", "折行", "check", None),
            ("imgId", "图片 id / 文件名", "entry", None),
            ("imgScale", "图片缩放 0.1-1", "entry", None),
        ]
        for key, label, kind, options in rows:
            line = ttk.Frame(self.props)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=label, width=16).pack(side="left")
            if kind == "combo":
                var = tk.StringVar()
                ttk.Combobox(line, textvariable=var, values=options, width=18,
                             state="readonly").pack(side="left", fill="x", expand=True)
            elif kind == "check":
                var = tk.BooleanVar()
                ttk.Checkbutton(line, variable=var).pack(side="left")
            else:
                var = tk.StringVar()
                entry = ttk.Entry(line, textvariable=var, width=20)
                entry.pack(side="left", fill="x", expand=True)
            var.trace_add("write", lambda *_a, k=key: self.on_prop_change(k))
            self.var_cache[key] = var
        ttk.Button(self.props, text="编辑随机台词行（文本 + 权重）…",
                   command=self.edit_random_lines).pack(anchor="w", pady=(6, 0))
        ttk.Button(self.props, text="从图片文件添加…", command=self.pick_image).pack(anchor="w", pady=2)
        ttk.Button(self.props, text="把「文本」存成模块库模块", command=self.save_to_lib).pack(anchor="w", pady=2)

    # ---------------- 数据访问 ----------------
    def current_item(self) -> dict | None:
        if 0 <= self.item_index < len(self.items):
            return self.items[self.item_index]
        return None

    def item_modules(self) -> list:
        item = self.current_item()
        if not item:
            return []
        if item.get("kind") == "custom":
            item.setdefault("modules", [])
            return item["modules"]
        return []

    def current_module(self) -> dict | None:
        mods = self.item_modules()
        if 0 <= self.module_index < len(mods):
            return mods[self.module_index]
        return None

    # ---------------- 刷新 ----------------
    def refresh_all(self) -> None:
        self.refresh_items()
        self.refresh_modules()
        self.refresh_props()
        self.refresh_preview()

    def refresh_items(self) -> None:
        self.item_list.delete(0, tk.END)
        for index, item in enumerate(self.items):
            kind = item.get("kind") or "normal"
            label = {"normal": "默认余额内容", "random": "随机台词段", "custom": "自定义模块",
                     "choice": "并列步骤（带权重）"}.get(kind, str(kind))
            if kind == "custom":
                label += "（%d 个模块）" % len(item.get("modules") or [])
            if kind == "choice":
                label += "（%d 个候选）" % len(item.get("options") or [])
            self.item_list.insert(tk.END, "%d. %s" % (index + 1, label))
        if self.items:
            self.item_index = min(self.item_index, len(self.items) - 1)
            self.item_list.selection_clear(0, tk.END)
            self.item_list.selection_set(self.item_index)
        else:
            self.item_index = 0
        self.item_list.delete(0, tk.END) if not self.items else None

    def refresh_modules(self) -> None:
        self.module_list.delete(0, tk.END)
        for index, mod in enumerate(self.item_modules()):
            kind = str(mod.get("type") or "text")
            text = str(mod.get("text") or mod.get("tpl") or mod.get("imgId") or "")
            if kind == "random":
                text = "%d 条随机" % len(mod.get("lines") or [])
            self.module_list.insert(tk.END, "%d. [%s] %s" % (index + 1, kind, text[:18]))
        self.lib_list.delete(0, tk.END)
        for entry in self.lib:
            self.lib_list.insert(tk.END, "%s：%s" % (entry.get("name"), str(entry.get("module", {}).get("text") or "")[:14]))
        self.tap_var.set(self.tap_advance)

    def refresh_props(self) -> None:
        mod = self.current_module() or {}
        for key, var in self.var_cache.items():
            value = mod.get(key, "")
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            else:
                var.set("" if value in (None, False) else str(value))

    def refresh_preview(self) -> None:
        item = self.current_item()
        self.preview.delete("all")
        self.preview.create_text(10, 10, anchor="nw", fill="#666",
                                 text="选中项预览（原版模块规则渲染）")
        if not item:
            return
        values = {"balance": data.money(1.99), "today": data.money(0.43),
                  "peak": "高峰时段", "session": "当前对话", "cost": "0.2984"}
        try:
            if item.get("kind") == "custom":
                balloon, content = card.render_bubble_modules(
                    item.get("modules") or [], self.assets, self.balloon_width,
                    values=values, split=True, image_dirs=self.image_dirs)
            elif item.get("kind") == "random":
                lines = presets.pick_random_lines()
                if isinstance(lines, dict):
                    self.preview.create_text(10, 40, anchor="nw", fill="#666",
                                             text="（抽到了 gif 组：挂件会直接放 rua 动图）")
                    return
                balloon, content = gfx.render_bubble(lines, width=self.balloon_width, split=True)
            else:
                slots = [{"t": "DeepSeek 余额", "s": "A"},
                         {"t": values["balance"], "s": "B"},
                         {"t": "今日已用 %s" % values["today"], "s": "C"}]
                balloon, content = gfx.render_bubble(slots, width=self.balloon_width, split=True)
        except Exception as exc:            # 编辑器不能因为一张图挂了就崩
            self.preview.create_text(10, 40, anchor="nw", fill="#c00", text="预览失败：%s" % exc)
            return
        merged = Image.alpha_composite(balloon, content).convert("RGBA")
        scale = min(1.0, 520.0 / max(1, merged.width), 230.0 / max(1, merged.height))
        if scale < 1.0:
            merged = merged.resize((int(merged.width * scale), int(merged.height * scale)), Image.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(merged)
        self.preview.create_image(10, 30, anchor="nw", image=self.preview_photo)

    # ---------------- 事件 ----------------
    def on_pick_item(self, _event=None) -> None:
        selection = self.item_list.curselection()
        if selection:
            self.item_index = selection[0]
            self.module_index = 0
            self.refresh_modules()
            self.refresh_props()
            self.refresh_preview()

    def on_pick_module(self, _event=None) -> None:
        selection = self.module_list.curselection()
        if selection:
            self.module_index = selection[0]
            self.refresh_props()

    def on_tap_toggle(self) -> None:
        self.tap_advance = bool(self.tap_var.get())
        self.dirty = True

    def on_prop_change(self, key: str) -> None:
        mod = self.current_module()
        if mod is None:
            return
        var = self.var_cache[key]
        value = var.get()
        if isinstance(var, tk.BooleanVar):
            if value:
                mod[key] = True
            else:
                mod.pop(key, None)
        else:
            text = str(value).strip()
            if key in ("size", "imgScale", "row"):
                if not text:
                    mod.pop(key, None)
                else:
                    try:
                        mod[key] = int(float(text)) if key != "imgScale" else float(text)
                    except ValueError:
                        return
            elif text:
                mod[key] = text
            else:
                mod.pop(key, None)
        self.dirty = True
        self.refresh_modules()
        self.refresh_preview()

    def add_item(self, kind: str) -> None:
        if kind == "custom":
            self.items.append({"kind": "custom", "modules": [{"type": "text", "text": "新模块", "size": 20}]})
        elif kind == "choice":
            self.items.append({"kind": "choice", "options": [
                {"w": 1, "item": {"kind": "normal"}}, {"w": 1, "item": {"kind": "custom", "modules": []}}]})
        else:
            self.items.append({"kind": kind})
        self.item_index = len(self.items) - 1
        self.dirty = True
        self.refresh_all()

    def move_item(self, delta: int) -> None:
        target = self.item_index + delta
        if 0 <= self.item_index < len(self.items) and 0 <= target < len(self.items):
            self.items[self.item_index], self.items[target] = self.items[target], self.items[self.item_index]
            self.item_index = target
            self.dirty = True
            self.refresh_all()

    def delete_item(self) -> None:
        if 0 <= self.item_index < len(self.items):
            self.items.pop(self.item_index)
            self.item_index = max(0, self.item_index - 1)
            self.dirty = True
            self.refresh_all()

    def add_module(self) -> None:
        mods = self.item_modules()
        kind = self.add_type.get()
        if kind == "image":
            mods.append({"type": "image", "imgId": "bimg_money1", "imgScale": 0.4})
        elif kind == "random":
            mods.append({"type": "random", "size": 18, "lines": [{"t": "新台词", "w": 1}]})
        else:
            mods.append({"type": kind, "size": 20,
                         "tpl" if kind in ("balance", "today", "peak", "session") else "text":
                             ("{%s}" % kind) if kind in ("balance", "today", "peak", "session") else "新文本"})
        self.module_index = len(mods) - 1
        self.dirty = True
        self.refresh_modules()
        self.refresh_props()
        self.refresh_preview()

    def move_module(self, delta: int) -> None:
        mods = self.item_modules()
        target = self.module_index + delta
        if 0 <= self.module_index < len(mods) and 0 <= target < len(mods):
            mods[self.module_index], mods[target] = mods[target], mods[self.module_index]
            self.module_index = target
            self.dirty = True
            self.refresh_modules()
            self.refresh_props()
            self.refresh_preview()

    def delete_module(self) -> None:
        mods = self.item_modules()
        if 0 <= self.module_index < len(mods):
            mods.pop(self.module_index)
            self.module_index = max(0, self.module_index - 1)
            self.dirty = True
            self.refresh_modules()
            self.refresh_props()
            self.refresh_preview()

    def save_to_lib(self) -> None:
        mod = self.current_module()
        if not mod:
            messagebox.showinfo("模块库", "先在中间选一个模块", parent=self.win)
            return
        name = simpledialog.askstring("模块名", "给这个模块起个名字：", parent=self.win,
                                      initialvalue="模块%d" % (len(self.lib) + 1))
        if not name:
            return
        self.lib.append({"id": "m%d" % int(time.time() * 1000 % 10 ** 9),
                         "name": name[:20], "module": clone(mod)})
        self.dirty = True
        self.refresh_modules()

    def insert_from_lib(self) -> None:
        selection = self.lib_list.curselection()
        if not selection:
            return
        entry = self.lib[selection[0]]
        mods = self.item_modules()
        if not mods and self.current_item() is not None:
            self.current_item()["kind"] = "custom"
            self.current_item()["modules"] = mods
        mods.append(clone(entry.get("module") or {}))
        self.module_index = len(mods) - 1
        self.dirty = True
        self.refresh_all()

    def delete_lib(self) -> None:
        selection = self.lib_list.curselection()
        if selection:
            self.lib.pop(selection[0])
            self.dirty = True
            self.refresh_modules()

    def edit_random_lines(self) -> None:
        mod = self.current_module()
        if not mod:
            return
        if mod.get("type") != "random":
            messagebox.showinfo("随机台词", "先把类型改成 random", parent=self.win)
            return
        win = tk.Toplevel(self.win)
        win.title("随机台词行（文本 + 权重）")
        win.geometry("520x420")
        win.attributes("-topmost", True)
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="每行一条，权重越大概率越高（原版 max(1, w||1) 加权）").pack(anchor="w")
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, pady=6)
        rows = []

        def add_row(text="", weight="1"):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=1)
            text_var = tk.StringVar(value=str(text))
            weight_var = tk.StringVar(value=str(weight))
            ttk.Entry(row, textvariable=text_var).pack(side="left", fill="x", expand=True)
            ttk.Label(row, text="权重").pack(side="left", padx=4)
            ttk.Entry(row, textvariable=weight_var, width=5).pack(side="left")
            ttk.Button(row, text="删", width=3,
                       command=lambda r=row: remove_row(r)).pack(side="left", padx=2)
            rows.append((row, text_var, weight_var))

        def remove_row(row):
            for index, (candidate, _t, _w) in enumerate(rows):
                if candidate is row:
                    rows.pop(index)
                    break
            row.destroy()

        for line in (mod.get("lines") or [{"t": "", "w": 1}]):
            add_row(line.get("t"), line.get("w", 1))

        def on_ok():
            collected = []
            for _row, text_var, weight_var in rows:
                text = text_var.get().strip()
                if not text:
                    continue
                try:
                    weight = max(1, int(float(weight_var.get() or 1)))
                except ValueError:
                    weight = 1
                collected.append({"t": text, "w": weight})
            mod["lines"] = collected or [{"t": "", "w": 1}]
            self.dirty = True
            win.destroy()
            self.refresh_modules()
            self.refresh_preview()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="加一行", command=lambda: add_row()).pack(side="left")
        ttk.Button(buttons, text="确定", command=on_ok).pack(side="right")
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="right", padx=4)

    def pick_image(self) -> None:
        mod = self.current_module()
        if not mod:
            return
        path = filedialog.askopenfilename(parent=self.win, title="选择图片（会复制到 whale-bubble-imgs）",
                                          filetypes=[("图片", "*.gif *.png *.jpg *.jpeg")])
        if not path:
            return
        target_dir = self.image_dirs[0]
        try:
            os.makedirs(target_dir, exist_ok=True)
            name = os.path.basename(path)
            with open(path, "rb") as src, open(os.path.join(target_dir, name), "wb") as dst:
                dst.write(src.read())
            mod["type"] = "image"
            mod["imgId"] = name
            mod.setdefault("imgScale", 0.4)
            self.dirty = True
            self.refresh_props()
            self.refresh_modules()
            self.refresh_preview()
        except Exception as exc:
            messagebox.showerror("复制失败", str(exc), parent=self.win)

    # ---------------- 保存 / 载入 ----------------
    def on_save(self) -> None:
        cfg = {"items": self.items, "lib": self.lib, "tapAdvance": self.tap_advance}
        if save_config(cfg):
            self.dirty = False
            self.status.config(text="已写入 %s" % config_path(), foreground="#2b7")
            if self.pet is not None:
                try:
                    self.pet.reload_bubble_config()
                except Exception:
                    pass
        else:
            self.status.config(text="写入失败（目录不可写？）", foreground="#c00")

    def on_reload(self) -> None:
        cfg = load_config() or {}
        self.items = clone(cfg.get("items")) if isinstance(cfg.get("items"), list) and cfg.get("items") else clone(DEFAULT_ITEMS)
        self.lib = clone(cfg.get("lib")) if isinstance(cfg.get("lib"), list) else []
        self.tap_advance = bool(cfg.get("tapAdvance"))
        self.item_index = self.module_index = 0
        self.dirty = False
        self.status.config(text="已重新载入", foreground="#555")
        self.refresh_all()

    def on_reset(self) -> None:
        self.items = clone(DEFAULT_ITEMS)
        self.item_index = self.module_index = 0
        self.dirty = True
        self.refresh_all()

    def on_import(self) -> None:
        path = filedialog.askopenfilename(parent=self.win, filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                self.items = clone(parsed["items"])
                self.lib = clone(parsed.get("lib") or [])
                self.tap_advance = bool(parsed.get("tapAdvance"))
                self.dirty = True
                self.refresh_all()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.win)

    def on_export(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.win, defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": 1, "items": self.items, "lib": self.lib, "tapAdvance": self.tap_advance},
                      handle, ensure_ascii=False, indent=2)


def _find_assets() -> str:
    import dsh_whale_pet as pet_module
    return pet_module.find_assets()


def open_editor(master, pet=None) -> BubbleEditor:
    return BubbleEditor(master, pet)
