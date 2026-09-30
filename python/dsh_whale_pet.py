# -*- coding: utf-8 -*-
"""DSH 小鲸鱼桌面挂件 —— Python 版（Bongo Cat Mver 风格）。

形态与 Bongo Cat Mver 一致：一个贴着桌面的小透明窗口，只有鲸鱼本体能点，
其余像素点击直接穿到桌面；可拖动、悬停会揉鲸鱼、按下有 Q 弹和音效；
右键出菜单，双击刷余额，滚轮调大小；支持开机自启。

数据与 DSH 插件共用（~/.dsh 下的 .credentials.yaml / .dshw-*.json），
所以它和 DSH 里的小鲸鱼看到的是同一个余额、同一本账。

用法：
    python dsh_whale_pet.py            # 正常启动
    python dsh_whale_pet.py --selftest # 无界面自检，打印 JSON 后退出
    pythonw dsh_whale_pet.py           # 无控制台窗口启动
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import simpledialog

from PIL import Image, ImageChops, ImageTk

import whale_bubble as gfx
import whale_card as card
import whale_colors as colors
import whale_data as data
import whale_presets as presets
from whale_audio import Audio

HERE = os.path.dirname(os.path.abspath(__file__))

def bezier_y(x1: float, y1: float, x2: float, y2: float, x: float, iterations: int = 18) -> float:
    """CSS 的 cubic-bezier(x1,y1,x2,y2) 在横坐标 x 处的 y。

    原版按压用的是 cubic-bezier(.34,1.56,.64,1) —— y1=1.56 会**冲过 1**，
    也就是那种按下之后弹回来的过冲手感。tkinter 没有 CSS 过渡，所以自己算。
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    t = x
    for _ in range(max(6, iterations)):
        t = (lo + hi) / 2.0
        xt = 3.0 * (1 - t) ** 2 * t * x1 + 3.0 * (1 - t) * t * t * x2 + t ** 3
        if xt < x:
            lo = t
        else:
            hi = t
    return 3.0 * (1 - t) ** 2 * t * y1 + 3.0 * (1 - t) * t * t * y2 + t ** 3


# 窗口比贴图大一圈，给 Q 弹留出溢出空间（多出来的都是键色 = 透明且不吃鼠标）
WINDOW_MARGIN = 1.32
# 1.0× 时鲸鱼本体的显示宽度（对齐 DSH Web 挂件里的观感：206px 左右）
BASE_DISPLAY_PX = 206
# 动画帧率：16ms ≈ 60fps。每帧只是换一张预渲染好的图，不做任何图像运算。
TICK_MS = 16
BALANCE_INTERVAL = 60.0
TURN_POLL_MS = 800

# 动画的缩放范围：悬停 +5%，按下 -11%。预渲染这张表，动画就只是"换图"，
# 平滑度不再受 Pillow 每次缩放/合成的影响。
# 动画参数 p：<0 按压、>0 回弹拉伸。原版按压规格（whale-widget.js）：
#   var SQUISH = 'scaleY(0.88) scaleX(1.05)'
#   .dshwv-body{transform-origin:50% 100%;transition:transform .22s cubic-bezier(.34,1.56,.64,1)}
# 即纵向压 12%、横向鼓 5%，0.22s 带**过冲回弹**的曲线，原点在底边中心。
PRESS_SQUASH_Y = 0.12      # scaleY 0.88
PRESS_SQUASH_X = 0.05      # scaleX 1.05
REBOUND_STRETCH_Y = 0.05   # 松开后的反向过冲（弹回来时略微拉长）
REBOUND_STRETCH_X = 0.02
PRESS_MS = 220             # 原版 .22s
PRESS_BEZIER = (0.34, 1.56, 0.64, 1.0)   # 原版 cubic-bezier
# 帧表覆盖 p ∈ [-过冲, +回弹]，41 档足够密（每档约 1.5% 缩放）
FRAME_STEPS = 41
FRAME_P_MIN = -1.25
FRAME_P_MAX = 0.25

TOP_UP_URL = "https://platform.deepseek.com/top_up"

# 系统提醒的优先级（原版 whaleSysQueueInsert：rank 小的先出）
BUBBLE_RANK_BUDGET = 1
BUBBLE_RANK_ALERT = 2
BUBBLE_RANK_COST = 3
BUBBLE_RANK_WAIT = 4
ALERT_TTL_MS = 6500      # 原版 USAGE_ALERT_TTL
QUOTE_TTL_MS = 5000      # 原版随机台词"总显示 5 秒自动收起"
BALLOON_TO_WHALE = 1.45  # 气泡宽度 / 鲸鱼本体宽度（由 DSniang02.png 与原版 SVG 比例得出）

# 吸附与翻转（对齐原版 v3 默认：上下 15%/左右 10%，上吸附默认关闭 = 0）
# 这里把上吸附默认打开（T=12），因为"吸到上边就倒挂"要靠它触发；
# flipText：镜像时是否连文字一起反向（原版为是；默认关，保证台词/金额还是能读的）
SNAP_DEFAULTS = {"on": True, "flip": True, "flipText": False, "upside": True,
                 "L": 10.0, "T": 12.0, "R": 10.0, "B": 15.0, "F": 50.0}
SNAP_PRESETS = {
    "窄": {"L": 5.0, "T": 8.0, "R": 5.0, "B": 8.0},
    "默认": {"L": 10.0, "T": 12.0, "R": 10.0, "B": 15.0},
    "宽": {"L": 20.0, "T": 18.0, "R": 20.0, "B": 25.0},
}

# GIF（图片台词）播放速度倍率。rua.gif 自带 20ms/帧（合 50fps），偏快，
# 所以档位以"放慢"为主：0.25× 就是 80ms/帧。
GIF_SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.5)

# 原版提醒卡片的默认内容（lib/index.js 的 usageSettingsDefaults，逐字段照搬）
ALERT_LINES_DEFAULT = [
    {"type": "text", "text": "老大~你的DS余额", "size": 5, "bold": True},
    {"type": "text", "text": "已经不足", "size": 5, "bold": True, "row": 2},
    {"type": "text", "text": "¥{below}", "size": 5, "bold": True, "color": "rouge", "row": 2},
    {"type": "text", "text": "啦~", "size": 5, "bold": True, "row": 2},
    {"type": "image", "imgId": "bimg_money1", "size": 6, "imgScale": 0.4},
    {"type": "link", "text": ">> 喂 点 米 <<", "url": TOP_UP_URL, "size": 4,
     "color": "#ffffff", "bgRgb": "indigo", "bold": True},
]
TURN_COST_LINES_DEFAULT = [
    {"type": "text", "text": "上一轮对话消耗:", "size": 8, "bold": True},
    {"type": "text", "text": "¥ {cost}", "size": 24, "bold": True, "color": "#e0433f"},
    {"type": "today", "size": 2, "tpl": "今日已用 {expense_ds}", "bgRgb": "indigo", "color": "#ffffff"},
]

QUOTES = [
    "摸摸鲸鱼娘~",
    "今天也要元气满满喵",
    "写代码辛苦了！",
    "余额还够，继续冲",
    "要不要休息一下？",
    "鲸鱼娘在看着你哦",
    "记得多喝水~",
]

# ---------------------------------------------------------------- Windows API
_user32 = getattr(ctypes, "windll", None)
_user32 = _user32.user32 if _user32 is not None else None

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x0002, 0x0001, 0x0010, 0x0020
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),        # 去掉任务栏后的可用区域
        ("dwFlags", wt.DWORD),
    ]


def hwnd_of(window) -> int:
    """取 Tk 窗口真正的顶层 HWND（overrideredirect 下 winfo_id 是子窗口）。"""
    if _user32 is None:
        return 0
    try:
        child = window.winfo_id()
        parent = _user32.GetParent(child)
        return parent or child
    except Exception:
        return 0


def get_exstyle(hwnd: int) -> int:
    if not hwnd or _user32 is None:
        return 0
    return int(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE))


def set_exstyle(hwnd: int, style: int) -> None:
    if not hwnd or _user32 is None:
        return
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)


# ---------------------------------------------------------------- 高清 DPI
def enable_dpi_awareness() -> str:
    """声明 DPI 感知，让窗口按物理像素渲染。

    不声明的话，在 125%/150% 缩放的屏幕上 Windows 会把整个窗口**位图拉伸**，
    结果就是糊；声明之后我们自己按 DPI 放大贴图与字号，出来是真清晰。
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
        return "per-monitor"
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()        # 老系统的系统级 DPI 感知
        return "system"
    except Exception:
        return "none"


def dpi_of_window(hwnd: int = 0) -> int:
    """窗口所在显示器的 DPI（96 = 100%）。拿不到就退回系统 DPI。"""
    if _user32 is not None and hwnd:
        try:
            value = int(_user32.GetDpiForWindow(hwnd))
            if value > 0:
                return value
        except Exception:
            pass
    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        return 96


# ---------------------------------------------------------------- 开机自启
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "DSHWhalePet"


def autostart_command() -> str:
    exe = sys.executable or "python.exe"
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pythonw):
        exe = pythonw
    return '"%s" "%s"' % (exe, os.path.join(HERE, "dsh_whale_pet.py"))


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return bool(value)
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 贴图缓存
class Sprites:
    """按缩放档位缓存贴图。动画每帧都要换图，缓存是必须的。

    源图是 610×610 且四周有透明留白，所以缩放的基准取**内容包围盒**，
    这样 1.0× 出来的就是鲸鱼本体的大小，而不是整张画布的大小。
    """

    def __init__(self, assets: str, log):
        self.assets = assets
        self.log = log
        self.base_path = None
        for name in ("DSniang1.png", "DSniang02.png", "DSH2.png"):
            path = os.path.join(assets, name)
            if os.path.isfile(path):
                self.base_path = path
                break
        if not self.base_path:
            raise RuntimeError("assets 里找不到鲸鱼图（DSniang1.png）")
        self.base = Image.open(self.base_path).convert("RGBA")

        # 内容包围盒（去掉四周透明留白）——缩放与窗口尺寸都以它为准
        bbox = self.base.getchannel("A").getbbox() or (0, 0, self.base.width, self.base.height)
        self.content_bbox = bbox
        self.content_size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        self.content_center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

        self.rua_path = os.path.join(assets, "rua.gif")
        self._rua_frames: list[Image.Image] = []
        self._rua_width = 0

    @property
    def base_size(self) -> tuple[int, int]:
        return self.base.size

    def rua_frames(self, target_width: int = 120) -> list:
        """气泡用的"图片台词"动图帧 (帧, 时长ms)（懒加载；宽度变了会重新生成）。"""
        if self._rua_frames and self._rua_width != target_width:
            self._rua_frames = []
        if not self._rua_frames and os.path.isfile(self.rua_path):
            self._rua_frames = gfx.render_rua_bubble_frames(self.rua_path, target_width)
            self._rua_width = target_width
        return self._rua_frames

    def scaled(self, pixel_scale_x: float, pixel_scale_y: float) -> Image.Image:
        """按 (横向, 纵向) 像素缩放系数渲染一张键色图（支持非等比，用于 Q 弹）。"""
        size = (max(1, int(round(self.base.width * pixel_scale_x))),
                max(1, int(round(self.base.height * pixel_scale_y))))
        return gfx.flatten(self.base.resize(size, Image.LANCZOS))


# ---------------------------------------------------------------- 气泡
class Bubble:
    def __init__(self, root: tk.Tk):
        self.win = tk.Toplevel(root)
        self.win.title("DSH 小鲸鱼挂件-气泡")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=gfx.KEY_HEX)
        try:
            self.win.wm_attributes("-transparentcolor", gfx.KEY_HEX)
        except Exception:
            pass
        self.canvas = tk.Canvas(self.win, bg=gfx.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo = None
        self.hide_job = None
        self.frame_job = None
        self.frames: list = []
        self.frame_index = 0
        self.frame_speed = 1.0
        self.deadline = 0.0
        self.links: list[dict] = []
        self.anim_job = None
        self.anim = None
        # 点击语义与原版一致：点泡泡 = 推进/收起（由挂件回调处理）
        self.on_bubble_click = None
        self.canvas.bind("<Button-1>", self._on_click)
        self.win.withdraw()

    def _on_click(self, event) -> None:
        """点泡泡：先看是不是点到按钮（原版 link 模块），否则交给挂件的"推进/收起"。"""
        for link in self.links:
            x, y, width, height = link.get("rect", (0, 0, 0, 0))
            if x <= event.x <= x + width and y <= event.y <= y + height:
                try:
                    webbrowser.open(str(link.get("url")))
                except Exception:
                    pass
                self.hide()
                return
        if callable(self.on_bubble_click):
            self.on_bubble_click()
        else:
            self.hide()

    # ---------------- 原版式弹出动画 ----------------
    # 原版：气球三层 .dshwv-b2/.dshwv-b1/.dshwv-bshape 从 scale(.7) 依次 0/0.13/0.26s
    # 充气（各 0.2s），文字 .dshwv-text 延迟 0.36s 淡入 0.16s；收起时延迟反向。
    #
    # tkinter 侧的关键约束：色键透明**没有半透明**，只有全透/全不透 —— 把半透明的图贴到
    # 键色底上只会混出品红鬼影。所以这里分两条路走：
    #   · 缩放/成形 → 重绘（内容始终不透明，flatten 的二值化 alpha 保证硬边）
    #   · 淡入淡出   → 窗口级 `-alpha`（已验证与 -transparentcolor 共存，flags 双开）
    OPEN_MS = 460
    TEXT_DELAY_MS = 360        # 原版：.dshwv-text transition-delay .36s
    TEXT_FADE_MS = 160         # 原版：opacity .16s ease
    CLOSE_MS = 320
    FRAME_MS = 33

    def show_layers(self, balloon: Image.Image, content: Image.Image, x: int, y: int,
                    links: list[dict] | None = None, sync_text: bool = False) -> None:
        """分层弹出：气球从 0.7 鼓起来，文字按原版时序淡入（0.36s 起、0.16s 内）。

        `sync_text=True` 时文字与气球同时开始显现（可选偏好；原版是错时的）。
        """
        self._stop_frames()
        if self.hide_job:
            try:
                self.win.after_cancel(self.hide_job)
            except Exception:
                pass
            self.hide_job = None
        self.links = []
        self.anim = {"balloon": balloon, "content": content, "links": list(links or []),
                     "x": x, "y": y, "phase": "open", "t0": time.perf_counter(),
                     "sync": bool(sync_text)}
        self.win.geometry("%dx%d+%d+%d" % (balloon.width, balloon.height, x, y))
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self._set_alpha(0.35)
        self._anim_tick()

    def _set_alpha(self, value: float) -> None:
        """窗口整体透明度（色键仍然生效，已验证）。"""
        try:
            self.win.wm_attributes("-alpha", max(0.02, min(1.0, float(value))))
        except Exception:
            pass

    def _anim_tick(self) -> None:
        state = self.anim
        if not state:
            return
        elapsed = (time.perf_counter() - state["t0"]) * 1000.0
        if state["phase"] == "open":
            inflate = min(1.0, elapsed / float(self.OPEN_MS))
            ease = 1.0 - (1.0 - inflate) ** 3        # ease-out：先快后慢，像被吹起来
            scale = 0.7 + 0.3 * ease
            alpha = 0.35 + 0.65 * min(1.0, ease * 1.6)
            if state.get("sync"):
                content_fade = min(1.0, elapsed / 220.0)
                done = inflate >= 1.0 and content_fade >= 1.0
            else:
                content_fade = min(1.0, max(0.0, (elapsed - self.TEXT_DELAY_MS) / float(self.TEXT_FADE_MS)))
                done = inflate >= 1.0 and content_fade >= 1.0
        else:
            p = min(1.0, elapsed / float(self.CLOSE_MS))
            ease = p * p                             # ease-in：收起比打开利落
            scale = 1.0 - 0.3 * ease
            alpha = 1.0 - ease
            # 文字和气球**一起**淡出（之前是过半就把文字切掉，看着像断成两半）
            content_fade = 1.0 - ease
            done = p >= 1.0

        self._blit(self._compose_layers(state["balloon"], state["content"], scale, content_fade))
        self._set_alpha(alpha)
        if done:
            if state["phase"] == "close":
                self.anim = None
                self.win.withdraw()
                self._set_alpha(1.0)
                return
            self.links = state["links"]              # 动画结束才接受点击
        self.anim_job = self.win.after(self.FRAME_MS, self._anim_tick)

    def _compose_layers(self, balloon: Image.Image, content: Image.Image, scale: float,
                        content_fade: float = 1.0) -> Image.Image:
        """按缩放重绘：气球层 + 内容层（文字/图片）。

        色键透明没有半透明，所以：
          · 缩放 → 重绘（flatten 的二值化 alpha 保证硬边、不出品红）
          · 淡入淡出 → 整体交给窗口 `-alpha`
          · **文字自己的淡入淡出** → 把内容颜色朝椭圆的白色混过去（在白色椭圆上等价于透明度）
        """
        width, height = balloon.size
        out = Image.new("RGB", (width, height), gfx.KEY_RGB)
        target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        offset = ((width - target[0]) // 2, (height - target[1]) // 2)
        out.paste(gfx.flatten(balloon.resize(target, Image.LANCZOS)), offset)
        if content_fade > 0.01:
            layer = content.resize(target, Image.LANCZOS)
            if content_fade < 0.999:
                alpha = layer.getchannel("A")
                white = Image.new("RGB", layer.size, (255, 255, 255))
                layer = Image.blend(layer.convert("RGB"), white, 1.0 - content_fade)
                layer = layer.convert("RGBA")
                layer.putalpha(alpha)
            # 必须带遮罩贴：否则内容四周的键色会把底下的椭圆整块盖掉
            mask = layer.getchannel("A").point(lambda v: 255 if v >= 28 else 0)
            out.paste(gfx.flatten(layer), offset, mask)
        return out

    def _blit(self, img: Image.Image) -> None:
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.config(width=img.width, height=img.height)
        self.canvas.itemconfig(self.item, image=self.photo)

    def _stop_anim(self) -> None:
        if self.anim_job:
            try:
                self.win.after_cancel(self.anim_job)
            except Exception:
                pass
            self.anim_job = None
        self.anim = None

    def update_layers(self, balloon: Image.Image, content: Image.Image,
                      links: list[dict] | None = None) -> None:
        """就地换掉气泡内容，**不重播**弹出动画 —— 翻转/倒挂/缩放时同步朝向用。"""
        if self.anim is not None:
            self.anim["balloon"] = balloon
            self.anim["content"] = content
            self.anim["links"] = list(links or [])
            return
        self.links = list(links or [])
        self._blit(self._compose_layers(balloon, content, 1.0, 1.0))

    def show(self, img: Image.Image, x: int, y: int, ms: int, auto_hide: bool = True,
             links: list[dict] | None = None) -> None:
        self._stop_anim()
        self.links = list(links or [])
        self._set_alpha(1.0)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.config(width=img.width, height=img.height)
        self.canvas.itemconfig(self.item, image=self.photo)
        self.win.geometry("%dx%d+%d+%d" % (img.width, img.height, x, y))
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        if self.hide_job:
            try:
                self.win.after_cancel(self.hide_job)
            except Exception:
                pass
            self.hide_job = None
        if auto_hide and ms > 0:
            self.hide_job = self.win.after(max(400, ms), self.hide)

    def show_frames(self, frames: list, x: int, y: int, ms: int, speed: float = 1.0) -> None:
        """播放动图气泡（"图片台词"）；frames = [(帧, 时长ms)]，speed 为速度倍率。"""
        self._stop_frames()
        if not frames:
            return
        self.frames = list(frames)
        self.frame_index = 0
        self.frame_speed = max(0.1, float(speed or 1.0))
        self.deadline = time.time() + max(1.0, ms / 1000.0)
        self.show(self.frames[0][0], x, y, 0, auto_hide=False)
        self._schedule_frame(x, y)

    def _schedule_frame(self, x: int, y: int) -> None:
        if not self.frames:
            return
        delay = int(self.frames[self.frame_index][1] / self.frame_speed)
        self.frame_job = self.win.after(max(20, delay), lambda: self._advance(x, y))

    def _advance(self, x: int, y: int) -> None:
        if not self.frames:
            return
        if time.time() >= self.deadline:
            self._stop_frames()
            self.hide()
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.show(self.frames[self.frame_index][0], x, y, 0, auto_hide=False)
        self._schedule_frame(x, y)

    def _stop_frames(self) -> None:
        if self.frame_job:
            try:
                self.win.after_cancel(self.frame_job)
            except Exception:
                pass
            self.frame_job = None
        self.frames = []

    def hide(self, animate: bool = True) -> None:
        """收起：原版式反向收缩淡出；`animate=False` 立刻收起。"""
        self.hide_job = None
        self.links = []
        self._stop_frames()
        if animate and self.anim and self.anim.get("phase") == "open":
            self.anim["phase"] = "close"
            self.anim["t0"] = time.perf_counter()
            if not self.anim_job:
                self._anim_tick()
            return
        self._stop_anim()
        self._set_alpha(1.0)
        self.win.withdraw()

    @property
    def visible(self) -> bool:
        return bool(self.win.winfo_ismapped())

    @property
    def opening(self) -> bool:
        return bool(self.anim and self.anim.get("phase") == "open")


# ---------------------------------------------------------------- 主挂件
class WhalePet:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = data.read_size()
        self.state = data.read_state()
        self.assets = find_assets()
        self.log_path = self._pick_log_path()
        self._log("启动：assets=%s" % self.assets)

        self.audio = Audio(self.assets, log=self._log)
        self.sprites = Sprites(self.assets, log=self._log)

        # ---- 状态（优先级：本挂件自己的 state > DSH 插件设置 > 默认）----
        self.scale = float(self.state.get("scale") or self.cfg.get("scale") or 1.4)
        self.scale = max(0.4, min(4.0, self.scale))
        self.sound_on = bool(self.state.get("sound", self.cfg.get("sound", True)))
        self.volume = float(self.state.get("volume", self.cfg.get("vol", 0.7)))
        self.topmost = bool(self.state.get("topmost", True))
        # 全局穿透**不跨启动保留**：它会让整只挂件（含右键菜单）都不吃鼠标，
        # 一旦被记住就再也点不回来了 —— 每次启动都从"可交互"开始。
        self.click_through = False
        self.no_activate = bool(self.state.get("noActivate", False))
        self.turn_cost_on = bool(self.state.get("turnCostOn", self.cfg.get("turnCostOn", True)))
        self.turn_cost_ms = int(self.state.get("turnCostCloseMs", self.cfg.get("turnCostCloseMs", 3000)))
        # 余额预警（阈值可设）与 吸附/翻转
        self.alert = self._load_alert()
        self.alert_fired = False
        self.snap = self._load_snap()
        self.flip = bool(self.state.get("flip", False))
        self.upside_down = bool(self.state.get("upsideDown", False))
        self.gif_speed = float(self.state.get("gifSpeed", 1.0) or 1.0)
        # 文字与气泡是否同时出现（原版是错时的：小点 → 大点 → 椭圆 → 文字）
        self.sync_text = bool(self.state.get("syncText", False))
        # 自定义泡泡配置（与 DSH 网页端共用 .dshw-bubble.json）
        self.bubble_items_cfg: list | None = None
        self.bubble_tap_advance = False
        # 全局穿透**不跨启动保留**：它会让整只挂件（含右键菜单）都不吃鼠标，
        # 一旦被记住就再也点不回来了 —— 每次启动都从"可交互"开始。
        self.click_through = False

        # 高清 DPI：先按系统 DPI 估一个，窗口建好后再按窗口所在显示器校准
        self.dpi_aware = "unknown"
        self.dpi = dpi_of_window(0)
        self.dpi_scale = self.dpi / 96.0
        self._metrics()
        x, y = self._initial_position()
        self.root.overrideredirect(True)
        self.root.geometry("%dx%d+%d+%d" % (self.win_w, self.win_h, x, y))
        self.root.configure(bg=gfx.KEY_HEX)
        self.root.attributes("-topmost", bool(self.topmost))
        try:
            self.root.wm_attributes("-transparentcolor", gfx.KEY_HEX)
        except Exception as exc:
            self._log("transparentcolor 设置失败：%s" % exc)

        self.canvas = tk.Canvas(self.root, width=self.win_w, height=self.win_h,
                                bg=gfx.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo = None

        # ---- 动画状态 ----
        self.hover = False
        self.press = 0.0          # 逻辑按压状态（1 = 按住）
        self.squash = 0.0         # 当前形变量：0 常态 / 1 按到底 / <0 回弹拉伸
        self.squash_from = 0.0
        self.squash_to = 0.0
        self.press_t0 = time.perf_counter()
        self.press_span = PRESS_MS / 1000.0
        self.last_tick = 0.0
        self.dpi_check_at = 0.0
        self.frame_index = -1

        # ---- 交互状态 ----
        self.drag_origin = None
        self.dragging = False
        self.press_pos = None
        self.press_time = 0.0

        self.bubble = Bubble(self.root)
        self.bubble.on_bubble_click = self.on_bubble_click
        # 系统提醒队列 + 手动台词轮次（对齐原版语义）
        self.sys_queue: list[dict] = []
        self.sys_current: dict | None = None
        self.bubble_ttl_job = None
        self.bubble_seq_idx = 0
        # 当前气泡的重绘信息（拖动跟随 / 翻转同步用）
        self.bubble_spec: dict | None = None
        self.queue: queue.Queue = queue.Queue()
        self.fetching = False
        self.balance = None
        self.usage = data.read_usage()
        self.turn_seq = data.turn_seq()
        self.last_balance_at = 0.0

        # ---- Win32 扩展样式 ----
        self.root.update_idletasks()
        self.hwnd = hwnd_of(self.root)
        self._apply_styles()

        # ---- 高清 DPI 校准 + 吸附/翻转 + 预渲染动画帧表 ----
        self._sync_dpi(initial=True)
        self.apply_snap_and_flip(persist=False)      # 启动时若落在吸附区/翻转区，先摆正
        self._build_frame_table()
        self.reload_bubble_config()                  # 自定义泡泡配置（可选）
        self._log("DPI 检测：dpi=%d scale=%.2f hwnd=%s 窗口=%dx%d s屏幕=%dx%d"
                  % (self.dpi, self.dpi_scale, self.hwnd, self.win_w, self.win_h,
                     self.root.winfo_screenwidth(), self.root.winfo_screenheight()))

        self.started_at = time.time()

        # ---- 菜单 ----
        self.var_top = tk.BooleanVar(value=self.topmost)
        self.var_through = tk.BooleanVar(value=self.click_through)
        self.var_sound = tk.BooleanVar(value=self.sound_on)
        self.var_noact = tk.BooleanVar(value=self.no_activate)
        self.var_autostart = tk.BooleanVar(value=autostart_enabled())
        self.var_turn = tk.BooleanVar(value=self.turn_cost_on)
        self.var_alert = tk.BooleanVar(value=bool(self.alert.get("on", True)))
        self.var_snap = tk.BooleanVar(value=bool(self.snap.get("on", True)))
        self.var_flip = tk.BooleanVar(value=bool(self.snap.get("flip", True)))
        self.menu = self._build_menu()

        # ---- 事件 ----
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.refresh_balance(bubble=True))
        self.canvas.bind("<Enter>", self.on_enter)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<Button-3>", self.on_menu)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.root.bind("<Escape>", lambda _e: self.quit())

        self.draw(force=True)
        self.refresh_balance(bubble=False)
        self.root.after(TICK_MS, self.tick)
        self.root.after(TURN_POLL_MS, self.poll_turn)

    # ---------------- 基础 ----------------
    @staticmethod
    def _pick_log_path() -> str:
        """日志优先写进 ~/.dsh；不可写（权限/沙箱）就退回脚本目录，绝不因为日志崩溃。"""
        for candidate in (data.dsh_path(".dshw-py-pet.log"), os.path.join(HERE, "dsh-whale-pet.log")):
            try:
                os.makedirs(os.path.dirname(candidate), exist_ok=True)
                with open(candidate, "a", encoding="utf-8"):
                    pass
                return candidate
            except Exception:
                continue
        return os.devnull

    def _log(self, message: str) -> None:
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + message
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def _metrics(self) -> None:
        """由 scale 与 DPI 推出「图片像素缩放」与窗口尺寸（基准＝内容包围盒，不是整张画布）。"""
        cw, ch = self.sprites.content_size
        self.img_scale = (BASE_DISPLAY_PX * self.scale * self.dpi_scale) / float(max(1, cw))
        self.win_w = max(32, int(round(cw * self.img_scale * WINDOW_MARGIN)))
        self.win_h = max(32, int(round(ch * self.img_scale * WINDOW_MARGIN)))
        self.pad = max(2, int(round(ch * self.img_scale * 0.02)))
        # 气泡宽度：原版里气泡 SVG 的宽度 = 挂件盒子宽度，且椭圆(746/1026)约为
        # 鲸鱼本体的 1.45 倍 —— 这里按同一比例换算，气泡与鲸鱼的相对大小才和原版一致。
        self.balloon_width = max(160, int(round(cw * self.img_scale * BALLOON_TO_WHALE)))

    def _sync_dpi(self, initial: bool = False) -> bool:
        """按窗口所在显示器校准 DPI（跨屏拖动后可能不同）。"""
        dpi = dpi_of_window(self.hwnd)
        changed = (not initial) and dpi != self.dpi
        self.dpi = dpi
        self.dpi_scale = dpi / 96.0
        if initial or changed:
            self._metrics()
        return changed

    # ---------------- 配置：余额预警 / 吸附 ----------------
    def _usage_settings(self) -> dict:
        """DSH 账本里的用量设置（预警内容、每轮消耗内容都由它来）。"""
        ledger = data.read_usage()
        settings = ledger.get("settings") if isinstance(ledger.get("settings"), dict) else {}
        return settings

    def _load_alert(self) -> dict:
        """余额预警：以 DSH 的 settings.alert 为底，本挂件自己的 state 覆盖。

        原版默认 {on: true, below: 5}；阈值与开关在本挂件的菜单里也能改，
        改完只写自己的 state，**不动** DSH 的账本文件。
        """
        base = self._usage_settings().get("alert")
        base = base if isinstance(base, dict) else {}
        cfg = {
            "on": bool(base.get("on", True)),
            "below": float(base.get("below", 5) or 5),
            "ttlSec": float(base.get("ttlSec", 6) or 6),
            "lines": base.get("lines") if isinstance(base.get("lines"), list) else None,
        }
        mine = self.state.get("alert")
        if isinstance(mine, dict):
            if "on" in mine:
                cfg["on"] = bool(mine["on"])
            if "below" in mine:
                try:
                    cfg["below"] = float(mine["below"])
                except (TypeError, ValueError):
                    pass
        return cfg

    def _load_snap(self) -> dict:
        cfg = dict(SNAP_DEFAULTS)
        mine = self.state.get("snap")
        if isinstance(mine, dict):
            for key in cfg:
                if key in mine:
                    cfg[key] = mine[key]
        return cfg

    def _initial_position(self) -> tuple[int, int]:
        saved = self.state.get("pos")
        if isinstance(saved, (list, tuple)) and len(saved) == 2:
            try:
                return int(saved[0]), int(saved[1])
            except Exception:
                pass
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - self.win_w - int(self.win_w * 0.06)
        y = screen_h - self.win_h - int(self.win_h * 0.14)
        return max(0, x), max(0, y)

    def _apply_styles(self) -> None:
        if not self.hwnd:
            return
        style = get_exstyle(self.hwnd)
        style |= WS_EX_TOOLWINDOW | WS_EX_LAYERED
        if self.click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        if self.no_activate:
            style |= WS_EX_NOACTIVATE
        else:
            style &= ~WS_EX_NOACTIVATE
        set_exstyle(self.hwnd, style)

    # ---------------- 绘制 ----------------
    def _anim_p(self) -> float:
        """动画参数：<0 按压（-1 = 按到底），>0 回弹时的拉伸过冲。"""
        return max(FRAME_P_MIN, min(FRAME_P_MAX, -self.squash))

    @staticmethod
    def _scale_factors(p: float) -> tuple[float, float]:
        """把动画参数换成 (横向, 纵向) 缩放系数 —— 原版的 scaleX/scaleY 数值。"""
        if p <= 0:
            press = -p                                  # 0..1+
            return 1.0 + PRESS_SQUASH_X * press, 1.0 - PRESS_SQUASH_Y * press
        return 1.0 - REBOUND_STRETCH_X * p, 1.0 + REBOUND_STRETCH_Y * p

    def _sprite_placement(self, p: float):
        """统一的贴图摆放：返回 (贴图, kx, ky, paste_x, paste_y)。

        镜像、贴顶倒挂、Q 弹形变**都在这一个地方算** —— 之前把镜像算在别处、
        画的时候忘了应用，正是"贴左边朝向没变"那个 bug 的成因。
        """
        scale_x, scale_y = self._scale_factors(p)
        kx, ky = self.img_scale * scale_x, self.img_scale * scale_y
        sprite = self.sprites.scaled(kx, ky)
        base_w, base_h = self.sprites.base_size
        bbox = self.sprites.content_bbox
        center_x = (bbox[0] + bbox[2]) / 2.0
        if self.upside_down:
            # 贴顶倒挂：整体转 180°，并且改为"内容上沿贴窗口顶部"（像挂在天花板上）
            sprite = sprite.transpose(Image.ROTATE_180)
            center_x = base_w - center_x
            paste_y = self.pad - (base_h - bbox[3]) * ky
        else:
            if self.flip:
                sprite = sprite.transpose(Image.FLIP_LEFT_RIGHT)
                center_x = base_w - center_x
            paste_y = (self.win_h - self.pad) - bbox[3] * ky
        paste_x = self.win_w / 2.0 - center_x * kx
        return sprite, kx, ky, paste_x, paste_y

    def _compose(self, p: float) -> Image.Image:
        """把某一档动画合成成窗口整图（贴图缩放/旋转 + 对齐 + 键色底）。"""
        sprite, _kx, _ky, paste_x, paste_y = self._sprite_placement(p)
        canvas_img = Image.new("RGB", (self.win_w, self.win_h), gfx.KEY_RGB)
        canvas_img.paste(sprite, (int(round(paste_x)), int(round(paste_y))))
        return canvas_img

    def _frame_index_for(self, p: float) -> int:
        pos = (p - FRAME_P_MIN) / (FRAME_P_MAX - FRAME_P_MIN)
        return int(round(max(0.0, min(1.0, pos)) * (FRAME_STEPS - 1)))

    def _build_frame_table(self) -> None:
        """把动画的每一档**预先渲染**成窗口大小的整图。

        之后动画每帧只做一次 canvas.itemconfig —— 不再有 LANCZOS 缩放、色键合成、
        新建画布和 PhotoImage 重建。原来每帧十几毫秒的图像运算才是卡顿的根因；
        实测换帧开销从 ~10ms 降到 **0.01ms**。
        """
        started = time.perf_counter()
        table = []
        for index in range(FRAME_STEPS):
            p = FRAME_P_MIN + (FRAME_P_MAX - FRAME_P_MIN) * index / float(FRAME_STEPS - 1)
            table.append(ImageTk.PhotoImage(self._compose(p)))
        self.frame_table = table
        self.frame_build_ms = round((time.perf_counter() - started) * 1000.0, 1)
        self.frame_index = -1
        self.photo = table[self._frame_index_for(-self.squash)]   # 保活，别让 Tk 把图回收了

    def window_image(self) -> Image.Image:
        """当前这一帧的窗口整图（PIL），供预览/自检复用同一套合成逻辑。"""
        return self._compose(self._anim_p())

    def draw(self, force: bool = False) -> None:
        index = self._frame_index_for(self._anim_p())
        if not force and index == self.frame_index:
            return
        self.frame_index = index
        self.photo = self.frame_table[index]
        self.canvas.itemconfig(self.item, image=self.photo)

    # ---------------- 动画 ----------------
    def tick(self) -> None:
        self.tick_once()
        self.root.after(TICK_MS, self.tick)

    def tick_once(self) -> None:
        """一帧的工作（自检里直接调用，不排下一次）。

        按压用原版那条 0.22s / cubic-bezier(.34,1.56,.64,1) 的回弹曲线推进；
        每帧只算两个浮点数再换一张预渲染好的图，没有任何图像运算。
        另外每 2 秒检查一次 DPI（跨屏拖动会变）。
        """
        now = time.perf_counter()
        dt = min(0.1, now - self.last_tick) if self.last_tick else TICK_MS / 1000.0
        self.last_tick = now

        span = max(0.05, self.press_span)
        u = min(1.0, max(0.0, (now - self.press_t0) / span))
        eased = bezier_y(*PRESS_BEZIER, u)           # 带过冲：按下弹过 1.0 再回落
        self.squash = self.squash_from + (self.squash_to - self.squash_from) * eased
        self.draw()

        if now - self.dpi_check_at > 2.0:
            self.dpi_check_at = now
            if self._sync_dpi():
                anchor = self._anchor_point()
                self._place_from_anchor(*anchor)
                self._build_frame_table()
                self.apply_snap_and_flip(persist=False)
                self.draw(force=True)
                self._log("DPI 变化 -> %d (%d%%)" % (self.dpi, round(self.dpi_scale * 100)))

        while True:
            try:
                result = self.queue.get_nowait()
            except queue.Empty:
                break
            self.fetching = False
            if result.get("ok"):
                self.balance = result
                self.last_balance_at = time.time()
                self._check_alert()
            else:
                self._log("余额刷新失败：%s" % result.get("error"))

        if time.time() - self.last_balance_at > BALANCE_INTERVAL:
            self.refresh_balance(bubble=False)

    # ---------------- 鼠标 ----------------
    def on_enter(self, _event) -> None:
        self.hover = True

    def on_leave(self, _event) -> None:
        self.hover = False
        self.press = 0.0
        self._start_press_anim(0.0)

    def _start_press_anim(self, target: float) -> None:
        """开始一次按压/回弹过渡（原版 .22s cubic-bezier(.34,1.56,.64,1)）。"""
        self.squash_from = self.squash
        self.squash_to = target
        self.press_t0 = time.perf_counter()

    def on_press(self, event) -> None:
        self.press = 1.0
        self._start_press_anim(1.0)
        self.press_pos = (event.x_root, event.y_root)
        self.press_time = time.time()
        self.drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        self.dragging = False
        self.play_sound("press")

    def on_drag(self, event) -> None:
        if not self.drag_origin:
            return
        dx = event.x_root - (self.root.winfo_x() + self.drag_origin[0])
        dy = event.y_root - (self.root.winfo_y() + self.drag_origin[1])
        if not self.dragging and abs(dx) + abs(dy) > 4:
            self.dragging = True
        if self.dragging:
            self.root.geometry("+%d+%d" % (event.x_root - self.drag_origin[0], event.y_root - self.drag_origin[1]))
            self._follow_bubble()          # 气泡跟着一起跑

    def on_release(self, event) -> None:
        self.press = 0.0
        self._start_press_anim(0.0)
        was_drag = self.dragging
        self.drag_origin = None
        self.dragging = False
        if was_drag:
            self.apply_snap_and_flip()
            return
        self.play_sound("release")
        self.on_whale_click()
        _ = event

    def on_wheel(self, event) -> None:
        step = 0.1 if event.delta > 0 else -0.1
        self.set_scale(self.scale + step)

    def on_menu(self, event) -> None:
        self.press = 0.0
        self.var_top.set(self.topmost)
        self.var_through.set(self.click_through)
        self.var_sound.set(self.sound_on)
        self.var_noact.set(self.no_activate)
        self.var_autostart.set(autostart_enabled())
        self.var_turn.set(self.turn_cost_on)
        self.var_alert.set(bool(self.alert.get("on")))
        self.var_snap.set(bool(self.snap.get("on")))
        self.var_flip.set(bool(self.snap.get("flip")))
        self.var_upside.set(bool(self.snap.get("upside", True)))
        self.var_flip_text.set(bool(self.snap.get("flipText")))
        if hasattr(self, "var_sync_text"):
            self.var_sync_text.set(self.sync_text)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ---------------- 菜单 ----------------
    def _build_menu(self) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="刷新余额", command=lambda: self.refresh_balance(bubble=True))
        menu.add_command(label="今日已用 / 记账", command=lambda: self.show_bubble("today", 0))
        menu.add_separator()
        menu.add_checkbutton(label="音效", variable=self.var_sound, command=self.toggle_sound)
        menu.add_checkbutton(label="每轮消耗提示", variable=self.var_turn, command=self.toggle_turn_cost)
        menu.add_separator()
        menu.add_checkbutton(label="余额预警", variable=self.var_alert, command=self.toggle_alert)
        menu.add_command(label="预警阈值：余额 ≤ ¥%s…" % self._num(self.alert.get("below")),
                         command=self.ask_alert_below)
        menu.add_separator()
        menu.add_checkbutton(label="贴边吸附", variable=self.var_snap, command=self.toggle_snap)
        menu.add_checkbutton(label="越过中线镜像翻转", variable=self.var_flip, command=self.toggle_flip)
        self.var_upside = tk.BooleanVar(value=bool(self.snap.get("upside", True)))
        menu.add_checkbutton(label="吸到上边时倒挂（旋转 180°）", variable=self.var_upside,
                             command=self.toggle_upside)
        self.var_flip_text = tk.BooleanVar(value=bool(self.snap.get("flipText", False)))
        menu.add_checkbutton(label="镜像时文字也反向（原版样式）", variable=self.var_flip_text,
                             command=self.toggle_flip_text)
        snap_menu = tk.Menu(menu, tearoff=0)
        for name in SNAP_PRESETS:
            snap_menu.add_command(label="吸附区宽度：%s" % name,
                                  command=lambda n=name: self.set_snap_preset(n))
        snap_menu.add_separator()
        for percent in (25, 50, 75):
            snap_menu.add_command(label="翻转线：%d%%（屏宽）" % percent,
                                  command=lambda v=percent: self.set_flip_line(v))
        snap_menu.add_separator()
        snap_menu.add_command(label="立即贴边/校正朝向", command=self.apply_snap_and_flip)
        menu.add_cascade(label="吸附与翻转", menu=snap_menu)
        gif_menu = tk.Menu(menu, tearoff=0)
        for speed in GIF_SPEEDS:
            gif_menu.add_command(label="%s×%s" % (("%g" % speed), "（原速）" if speed == 1.0 else ""),
                                 command=lambda v=speed: self.set_gif_speed(v))
        menu.add_cascade(label="图片台词速度", menu=gif_menu)
        self.var_sync_text = tk.BooleanVar(value=self.sync_text)
        menu.add_checkbutton(label="文字与气泡同步出现（原版是错时的）", variable=self.var_sync_text,
                             command=self.toggle_sync_text)
        menu.add_separator()
        menu.add_command(label="编辑气泡…（与 DSH 共用配置）", command=self.open_bubble_editor)
        menu.add_command(label="重新载入气泡配置", command=lambda: (self.reload_bubble_config(),
                                                                  self.show_short("气泡配置已重载", 2000)))
        menu.add_separator()
        menu.add_checkbutton(label="始终置顶", variable=self.var_top, command=self.toggle_topmost)
        menu.add_checkbutton(label="全局穿透（整只挂件不吃鼠标）", variable=self.var_through, command=self.toggle_through)
        menu.add_checkbutton(label="点击不抢焦点", variable=self.var_noact, command=self.toggle_no_activate)
        menu.add_checkbutton(label="开机自启", variable=self.var_autostart, command=self.toggle_autostart)
        menu.add_separator()
        size_menu = tk.Menu(menu, tearoff=0)
        size_menu.add_command(label="放大", command=lambda: self.set_scale(self.scale + 0.15))
        size_menu.add_command(label="缩小", command=lambda: self.set_scale(self.scale - 0.15))
        size_menu.add_command(label="重置到 1.4×", command=lambda: self.set_scale(1.4))
        menu.add_cascade(label="大小", menu=size_menu)
        menu.add_command(label="回到右下角", command=self.reset_position)
        menu.add_separator()
        menu.add_command(label="打开数据目录", command=self.open_data_dir)
        menu.add_command(label="退出", command=self.quit)
        return menu

    def toggle_sound(self) -> None:
        self.sound_on = bool(self.var_sound.get())
        data.write_state({"sound": self.sound_on})

    def toggle_turn_cost(self) -> None:
        self.turn_cost_on = bool(self.var_turn.get())
        data.write_state({"turnCostOn": self.turn_cost_on})

    def toggle_topmost(self) -> None:
        self.topmost = bool(self.var_top.get())
        self.root.attributes("-topmost", self.topmost)
        data.write_state({"topmost": self.topmost})

    def toggle_through(self) -> None:
        self.click_through = bool(self.var_through.get())
        self._apply_styles()
        data.write_state({"clickThrough": self.click_through})

    def toggle_no_activate(self) -> None:
        self.no_activate = bool(self.var_noact.get())
        self._apply_styles()
        data.write_state({"noActivate": self.no_activate})

    def toggle_autostart(self) -> None:
        want = bool(self.var_autostart.get())
        ok = set_autostart(want)
        if not ok:
            self.var_autostart.set(not want)
            self.show_short("设置自启失败")
            return
        self.show_short("已开启开机自启" if want else "已关闭开机自启")

    # ---------------- 大小 / 位置 ----------------
    def _anchor_point(self) -> tuple[int, int]:
        """窗口底部锚点（底边中心）。改尺寸/改 DPI 时保持它不动，挂件就不会跳。"""
        return (self.root.winfo_x() + self.win_w // 2,
                self.root.winfo_y() + self.win_h - self.pad)

    def _place_from_anchor(self, center_x: int, bottom_y: int) -> None:
        x = center_x - self.win_w // 2
        y = bottom_y - self.win_h + self.pad
        self.canvas.config(width=self.win_w, height=self.win_h)
        self.root.geometry("%dx%d+%d+%d" % (self.win_w, self.win_h, x, y))

    def set_scale(self, scale: float) -> None:
        scale = max(0.4, min(4.0, float(scale)))
        anchor = self._anchor_point()
        self.scale = scale
        self._metrics()
        self._place_from_anchor(*anchor)
        self._build_frame_table()
        self.apply_snap_and_flip(persist=False)
        self.draw(force=True)
        self._refresh_bubble()               # 缩放后气泡尺寸也变了
        data.write_state({"scale": scale, "pos": [self.root.winfo_x(), self.root.winfo_y()]})

    def reset_position(self) -> None:
        self.state.pop("pos", None)
        x, y = self._initial_position()
        self.root.geometry("+%d+%d" % (x, y))
        data.write_state({"pos": [x, y]})
        self.apply_snap_and_flip()

    # ---------------- 吸附与翻转（对齐原版） ----------------
    def _content_screen_rect(self) -> tuple[float, float, float, float]:
        """鲸鱼本体（内容包围盒）当前在屏幕上的矩形 —— 吸附与气泡都以它为准。"""
        _sprite, kx, ky, paste_x, paste_y = self._sprite_placement(self._anim_p())
        base_w, base_h = self.sprites.base_size
        left, top, right, bottom = self.sprites.content_bbox
        if self.upside_down:
            left, right = base_w - right, base_w - left
            top, bottom = base_h - bottom, base_h - top
        elif self.flip:
            left, right = base_w - right, base_w - left
        win_x, win_y = self.root.winfo_x(), self.root.winfo_y()
        return (win_x + paste_x + left * kx, win_y + paste_y + top * ky,
                win_x + paste_x + right * kx, win_y + paste_y + bottom * ky)

    def apply_snap_and_flip(self, persist: bool = True) -> None:
        """贴边吸附 + 镜像翻转。

        吸附：鲸鱼本体进入左/右/上/下吸附区就贴到该边（角落可组合），
        吸附区宽度按显示器可用区域的百分比（原版 v3 默认 左右 10%、上 0%、下 15%）。
        翻转：鲸鱼中心越过翻转线（默认屏宽 50%）时整体水平镜像，回到右侧自动翻回来。
        """
        cfg = self.snap
        area_left, area_top, area_right, area_bottom = self.screen_work_area()
        area_w = max(1.0, float(area_right - area_left))
        area_h = max(1.0, float(area_bottom - area_top))
        margin = 2.0 * self.dpi_scale

        zone_l = area_w * float(cfg.get("L", 0)) / 100.0
        zone_r = area_w * float(cfg.get("R", 0)) / 100.0
        zone_t = area_h * float(cfg.get("T", 0)) / 100.0
        zone_b = area_h * float(cfg.get("B", 0)) / 100.0

        # 1) 先按当前姿态判断落在哪个吸附区
        snapped_top = False
        if cfg.get("on", True):
            left, top, right, bottom = self._content_screen_rect()
            if zone_t > 0 and top <= area_top + zone_t:
                snapped_top = True
            elif zone_b > 0 and bottom >= area_bottom - zone_b:
                snapped_top = False

        # 2) 姿态：吸到上边 → 倒挂；否则按翻转线决定左右镜像（倒挂时不再叠加镜像）
        want_upside = bool(cfg.get("upside", True)) and snapped_top
        want_flip = False
        if not want_upside and cfg.get("flip", True):
            left, _top, right, _bottom = self._content_screen_rect()
            line = area_left + area_w * float(cfg.get("F", 50)) / 100.0
            want_flip = ((left + right) / 2.0) < line
        if want_upside != self.upside_down or want_flip != self.flip:
            self.upside_down = want_upside
            self.flip = want_flip
            if getattr(self, "frame_table", None):   # 帧表还没建时，交给调用方统一建
                self._build_frame_table()
                self.draw(force=True)
            self._refresh_bubble()                   # 气泡跟着一起翻

        # 3) 再按（可能的）新姿态贴边
        if cfg.get("on", True):
            left, top, right, bottom = self._content_screen_rect()
            dx = dy = 0.0
            if zone_l > 0 and left <= area_left + zone_l:
                dx = (area_left + margin) - left
            elif zone_r > 0 and right >= area_right - zone_r:
                dx = (area_right - margin) - right
            if zone_t > 0 and top <= area_top + zone_t:
                dy = (area_top + margin) - top
            elif zone_b > 0 and bottom >= area_bottom - zone_b:
                dy = (area_bottom - margin) - bottom
            if dx or dy:
                self.root.geometry("+%d+%d" % (int(round(self.root.winfo_x() + dx)),
                                               int(round(self.root.winfo_y() + dy))))
        if persist:
            data.write_state({"pos": [self.root.winfo_x(), self.root.winfo_y()],
                              "flip": self.flip, "upsideDown": self.upside_down})

    def toggle_snap(self) -> None:
        self.snap["on"] = bool(self.var_snap.get())
        data.write_state({"snap": self.snap})
        if self.snap["on"]:
            self.apply_snap_and_flip()

    def toggle_flip(self) -> None:
        self.snap["flip"] = bool(self.var_flip.get())
        data.write_state({"snap": self.snap})
        if self.snap["flip"]:
            self.apply_snap_and_flip()
        elif self.flip:
            self.flip = False
            self._build_frame_table()
            self.draw(force=True)

    def set_snap_preset(self, name: str) -> None:
        self.snap.update(SNAP_PRESETS.get(name, {}))
        self.snap["on"] = True
        self.var_snap.set(True)
        data.write_state({"snap": self.snap})
        self.apply_snap_and_flip()

    def set_flip_line(self, percent: float) -> None:
        self.snap["F"] = float(percent)
        self.snap["flip"] = True
        self.var_flip.set(True)
        data.write_state({"snap": self.snap})
        self.apply_snap_and_flip()

    def toggle_flip_text(self) -> None:
        self.snap["flipText"] = bool(self.var_flip_text.get())
        data.write_state({"snap": self.snap})

    def toggle_upside(self) -> None:
        self.snap["upside"] = bool(self.var_upside.get())
        data.write_state({"snap": self.snap})
        self.apply_snap_and_flip()

    def set_gif_speed(self, speed: float) -> None:
        self.gif_speed = max(0.1, float(speed))
        data.write_state({"gifSpeed": self.gif_speed})
        self.show_short("图片台词速度 %g×" % self.gif_speed, 2000)

    # ---------------- 余额预警 ----------------
    def toggle_alert(self) -> None:
        self.alert["on"] = bool(self.var_alert.get())
        data.write_state({"alert": {"on": self.alert["on"], "below": self.alert["below"]}})
        if self.alert["on"]:
            self.alert_fired = False
            self._check_alert()
        else:
            self.alert_fired = True

    def ask_alert_below(self) -> None:
        value = simpledialog.askfloat(
            "余额预警", "余额低于多少时提醒？（元）",
            initialvalue=float(self.alert.get("below") or 5),
            minvalue=0.0, maxvalue=1000000.0, parent=self.root,
        )
        if value is None:
            return
        self.alert["below"] = float(value)
        self.alert_fired = False
        data.write_state({"alert": {"on": self.alert["on"], "below": self.alert["below"]}})
        self.show_short("预警阈值 ¥%s" % self._num(value), 2500)
        self._check_alert()

    def open_bubble_editor(self) -> None:
        """打开气泡编辑器（读写的就是 DSH 那份 .dshw-bubble.json）。"""
        try:
            import whale_editor
            whale_editor.open_editor(self.root, self)
        except Exception as exc:
            self._log("打开气泡编辑器失败：%s" % exc)
            self.show_short("编辑器打开失败：%s" % str(exc)[:24], 4000)

    def open_data_dir(self) -> None:
        try:
            os.startfile(data.dsh_home())  # noqa: S606
        except Exception as exc:
            self._log("打开数据目录失败：%s" % exc)

    # ---------------- 音效 ----------------
    def play_sound(self, kind: str) -> None:
        if not self.sound_on:
            return
        names = {
            "duck": {"press": "Ya1.mp3", "release": "Ya2.mp3"},
            "set1": {"press": "D1.mp3", "release": "D2.mp3"},
            "d1": {"press": "D1.mp3", "release": "D2.mp3"},
        }
        group = str(self.cfg.get("soundSet") or "duck")
        pick = names.get(group, names["duck"]).get(kind)
        if pick:
            self.audio.play(pick, self.volume)

    def play_task_end(self) -> None:
        if not self.sound_on:
            return
        for name in ("task-end-a.wav", "minecraft-exp-orb.wav"):
            if self.audio.play(name, self.volume):
                return

    # ---------------- 余额 / 记账 ----------------
    def refresh_balance(self, bubble: bool = True) -> None:
        if self.fetching:
            return
        self.fetching = True

        def worker():
            result = data.fetch_balance()
            self.queue.put(result)

        threading.Thread(target=worker, name="dshw-balance", daemon=True).start()
        if bubble:
            self.show_short("刷新中…")

    def refresh_local(self) -> None:
        self.usage = data.read_usage()

    def poll_turn(self) -> None:
        try:
            seq = data.turn_seq()
            if seq != self.turn_seq:
                first_seen = not self.turn_seq
                self.turn_seq = seq
                self.refresh_local()
                event = data.last_event(self.usage)
                # 只提示"本次启动之后"结束的轮次：否则挂件一启动就会把历史那轮弹出来
                ts = event.get("ts") if isinstance(event, dict) else None
                fresh = isinstance(ts, (int, float)) and (float(ts) / 1000.0) >= (self.started_at - 5.0)
                if event and self.turn_cost_on and fresh:
                    cost = event.get("cost")
                    tokens = event.get("tokens")
                    model = event.get("model") or ""
                    # 原版：每轮消耗进系统队列（rank 3），同档后入先出 ⇒ 新的置顶、旧的排队
                    self.push_system_bubble("cost", BUBBLE_RANK_COST,
                                            lambda c=cost, t=tokens, m=model: self.turn_cost_layers(c, t, m),
                                            self.turn_cost_ms)
                elif first_seen:
                    self._log("跳过启动前的历史轮次（seq=%s）" % seq)
                if fresh:
                    self.play_task_end()
        except Exception as exc:
            self._log("轮次轮询异常：%s" % exc)
        self.root.after(TURN_POLL_MS, self.poll_turn)

    def currency(self) -> str:
        if self.balance and self.balance.get("currency"):
            return str(self.balance["currency"])
        return str(self.usage.get("lastCurrency") or "CNY")

    @staticmethod
    def human_tokens(tokens: float) -> str:
        if tokens >= 1_000_000:
            return "%.2fM" % (tokens / 1_000_000.0)
        if tokens >= 1_000:
            return "%.1fK" % (tokens / 1_000.0)
        return str(int(tokens))

    # ---------------- 气泡 ----------------
    def whale_edges(self) -> tuple[float, float]:
        """鲸鱼本体在屏幕上的上沿与下沿 —— 气泡锚在它上面，而不是锚在窗口上。"""
        _left, top, _right, bottom = self._content_screen_rect()
        return top, bottom

    def screen_work_area(self) -> tuple[int, int, int, int]:
        """窗口所在显示器的可用区域（多屏、任务栏都算对）。"""
        if _user32 is not None and self.hwnd:
            try:
                monitor = _user32.MonitorFromWindow(self.hwnd, MONITOR_DEFAULTTONEAREST)
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def bubble_placement(self, width: int, height: int) -> tuple[int, int, str]:
        """气泡位置：默认挂在鲸鱼头顶正上方；上面放不下就翻到下方（尾巴朝上）。

        贴顶倒挂时鲸鱼的头朝下，所以气泡直接挂到它下面。
        """
        top, bottom = self.whale_edges()
        area_left, area_top, area_right, _area_bottom = self.screen_work_area()
        center_x = self.root.winfo_x() + self.win_w / 2.0
        gap = max(4, int(round(6 * self.dpi_scale)))

        if self.upside_down:
            tail, y = "up", bottom + gap
        else:
            tail = "down"
            y = top - height - gap
            if y < area_top + 4:
                tail = "up"
                y = bottom + gap
        x = center_x - width / 2.0
        x = max(area_left + 2, min(area_right - width - 2, x))
        return int(round(x)), int(round(y)), tail

    def _bubble_layers(self, slots: list, accent: bool = False):
        """气泡分层渲染（原版 SVG 气泡 + 原版三行结构内容），按需翻转与上下朝向。"""
        balloon, content = gfx.render_bubble(slots, width=self.balloon_width, accent=accent, split=True)
        x, y, tail = self.bubble_placement(balloon.width, balloon.height)
        if tail == "up":
            balloon, content = gfx.render_bubble(slots, width=self.balloon_width, accent=accent,
                                                 tail="up", split=True)
        if self.flip:
            # 气泡（尾巴缺口、小点的位置）跟着鲸鱼一起翻；文字是否也反由开关决定
            balloon = balloon.transpose(Image.FLIP_LEFT_RIGHT)
            if self.snap.get("flipText"):
                content = content.transpose(Image.FLIP_LEFT_RIGHT)
        return balloon, content, [], x, y

    def show_bubble_text(self, lines: list[str], ms: int, accent: bool = False) -> None:
        """直接弹一条文本气泡（不入系统队列）。"""
        balloon, content, links, x, y = self._bubble_layers(lines, accent)
        self._pop_layers(balloon, content, ms, links, x, y,
                         render=lambda: self._bubble_layers(lines, accent))

    # ---------------- 原版卡片式气泡 ----------------
    @staticmethod
    def _num(value) -> str:
        """数字去掉多余的 0：5.0 → 5，0.2984 → 0.2984。"""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value if value is not None else "")
        text = ("%.4f" % number).rstrip("0").rstrip(".")
        return text or "0"

    def _render_modules(self, modules: list[dict], values: dict | None, tail: str = "down"):
        """渲染卡片模块，返回 (气球层, 内容层, links)；镜像态下按需整块翻转。"""
        balloon, content, links = card.render_card(modules, self.assets, values=values,
                                                   ui_scale=self.dpi_scale, width=self.balloon_width,
                                                   tail=tail, split=True)
        if self.flip:
            balloon = balloon.transpose(Image.FLIP_LEFT_RIGHT)   # 气泡跟着一起翻
            if self.snap.get("flipText"):                        # 文字反向（原版样式）
                content = content.transpose(Image.FLIP_LEFT_RIGHT)
                width = content.width
                links = [{"url": item["url"],
                          "rect": (width - item["rect"][0] - item["rect"][2], item["rect"][1],
                                   item["rect"][2], item["rect"][3])}
                         for item in links]
        return balloon, content, links

    def _card_layers(self, modules: list[dict], values: dict | None):
        balloon, content, links = self._render_modules(modules, values)
        x, y, tail = self.bubble_placement(balloon.width, balloon.height)
        if tail == "up":
            balloon, content, links = self._render_modules(modules, values, tail="up")
        return balloon, content, links, x, y

    def alert_modules(self) -> list[dict]:
        """预警内容：优先用 DSH 里自定义过的 lines，否则原版默认。"""
        lines = self.alert.get("lines")
        return lines if lines else ALERT_LINES_DEFAULT

    def alert_layers(self):
        values = {"below": self._num(self.alert.get("below")), "amount": "", "cost": "", "session": ""}
        return self._card_layers(self.alert_modules(), values)

    def turn_cost_layers(self, cost, tokens, model):
        modules, values = self.turn_cost_modules(cost, tokens, model)
        return self._card_layers(modules, values)

    def turn_cost_modules(self, cost, tokens, model) -> tuple[list[dict], dict]:
        settings = self._usage_settings().get("turnCost")
        lines = None
        if isinstance(settings, dict) and isinstance(settings.get("lines"), list):
            lines = settings["lines"]
        values = {
            "cost": self._num(cost) if isinstance(cost, (int, float)) else "--",
            "expense_ds": data.money(data.today_usage(self.usage), self.currency()),
            "below": self._num(self.alert.get("below")),
            "amount": "",
            "session": "",
            "tokens": self.human_tokens(tokens) if isinstance(tokens, (int, float)) and tokens else "",
            "model": model or "",
        }
        return (lines or TURN_COST_LINES_DEFAULT), values

    def _check_alert(self) -> None:
        """余额预警：`balance > 0 且 balance <= 阈值` 时提醒一次；回升到阈值以上后重新武装。

        与原版 checkUsageAlerts 的判定一致（`<=`，且余额为 0/取不到时不提醒）。
        """
        if not self.alert.get("on"):
            return
        if not self.balance or not self.balance.get("ok"):
            return
        try:
            total = float(self.balance.get("total") or 0)
            below = float(self.alert.get("below") or 0)
        except (TypeError, ValueError):
            return
        if total <= 0 or below <= 0:
            return
        if total <= below:
            if not self.alert_fired:
                self.alert_fired = True
                self._log("余额预警触发：余额 %s <= 阈值 %s" % (total, below))
                self.push_system_bubble("alert", BUBBLE_RANK_ALERT, self.alert_layers, ALERT_TTL_MS)
        else:
            self.alert_fired = False

    def show_short(self, text: str, ms: int = 2500) -> None:
        self.show_bubble_text([text], ms)

    # ---------------- 气泡：原版的推送队列与点击语义 ----------------
    def push_system_bubble(self, kind: str, rank: int, layers_fn, ttl_ms: int) -> None:
        """系统提醒入队（对齐原版 whaleSysPush）。

        rank 小的先出：1 今日预算 / 2 余额预警 / 3 本轮消耗 / 4 等待交互；
        **同档「每轮消耗」后入先出**（新一轮插到旧的前面 ⇒ 新的置顶、旧的排队），
        其它档位先入先出。当前没有正在展示的提醒时立刻出队。
        """
        item = {"kind": kind, "rank": rank, "layers": layers_fn, "ttl": ttl_ms}
        if rank == BUBBLE_RANK_COST:
            # 同档后入先出：插到**已有消耗项之前** ⇒ 新的置顶、旧的排队（原版语义）
            position = 0
            for index, other in enumerate(self.sys_queue):
                if other["rank"] < rank:
                    position = index + 1
                else:
                    break
            self.sys_queue.insert(position, item)
        else:
            self.sys_queue.append(item)
            self.sys_queue.sort(key=lambda it: it["rank"])
        if self.sys_current is None:
            self._show_next_system()

    def _show_next_system(self) -> None:
        if not self.sys_queue:
            self.sys_current = None
            return
        item = self.sys_queue.pop(0)
        self.sys_current = item
        try:
            balloon, content, links, x, y = item["layers"]()
        except Exception as exc:
            self._log("系统提醒渲染失败：%s" % exc)
            self.sys_current = None
            self._show_next_system()
            return
        self._pop_layers(balloon, content, item["ttl"], links, x, y,
                         on_ttl=self._system_ttl, render=item["layers"])
        if item["kind"] in ("alert", "cost"):
            self.play_task_end()

    def _system_ttl(self) -> None:
        self.bubble_ttl_job = None
        self.bubble.hide()
        self._system_closed()

    def _system_closed(self) -> None:
        self.sys_current = None
        self._show_next_system()

    def on_bubble_click(self) -> None:
        """点泡泡：系统提醒 → 收起（接着放队列里的下一条）；手动台词 → 推进下一项/收起。"""
        self._cancel_ttl()
        if self.sys_current is not None:
            self.bubble.hide()
            self._system_closed()
            return
        self._advance_manual()

    def on_whale_click(self) -> None:
        """点鲸鱼（对齐原版 whaleClick）：

        系统提醒期间点鲸鱼**不动作**（要点泡泡才关）；
        没泡泡 → 从第 1 项开始；正显示第 1 项 → 只续时不清内容；第 2 项及以后 → 回到第 1 项。
        勾了「点按角色推进队列」(tapAdvance) 时，点鲸鱼改为**往后推进**一项。
        """
        if not self.cfg.get("bubbleOn", True):
            return
        if self.sys_current is not None:
            return
        if self.bubble_tap_advance:
            if not self.bubble.visible:
                self.bubble_seq_idx = 0
            self._advance_manual()
            return
        if not self.bubble.visible:
            self.bubble_seq_idx = 0
            self._advance_manual()
            return
        if self.bubble_seq_idx <= 1:
            self._reset_manual_ttl()
            return
        self.bubble_seq_idx = 0
        self._advance_manual()

    def manual_kinds(self) -> list[str]:
        """手动点击序列：原版是 第1项 余额默认内容 → 第2项 随机台词段。"""
        return ["balance", "quote"]

    # ---------------- 自定义泡泡配置（.dshw-bubble.json，与 DSH 共用） ----------------
    def reload_bubble_config(self) -> None:
        """读入 .dshw-bubble.json（与 DSH 网页端同一份）。"""
        try:
            import whale_editor
            cfg = whale_editor.load_config() or {}
        except Exception as exc:
            self._log("气泡配置读取失败：%s" % exc)
            cfg = {}
        items = cfg.get("items") if isinstance(cfg.get("items"), list) else None
        self.bubble_items_cfg = items if items else None
        self.bubble_tap_advance = bool(cfg.get("tapAdvance"))
        self._log("气泡配置：%s（tapAdvance=%s）"
                  % ("%d 项" % len(items) if items else "未配置（用默认序列）", self.bubble_tap_advance))

    def bubble_values(self) -> dict:
        """模块里的占位符取值（原版那套：{balance_ds} / {expense_ds} / {status} / {countdown} …）。"""
        total = None
        if self.balance and self.balance.get("ok"):
            try:
                total = float(self.balance.get("total"))
            except (TypeError, ValueError):
                total = None
        money = data.money(total, self.currency()) if total is not None else "--"
        today = data.money(data.today_usage(self.usage), self.currency())
        last = data.last_event(self.usage) or {}
        is_peak = self._peak_now()
        return {
            "balance": money, "balance_ds": money,
            "today": today, "expense_ds": today,
            "status": "高峰时段" if is_peak else "空闲时段",
            "countdown": self.peak_countdown(),
            "peak": "高峰时段" if is_peak else "",
            "off": "" if is_peak else "空闲时段",
            "session": "当前对话",
            "cost": self._num(last.get("cost")) if isinstance(last.get("cost"), (int, float)) else "--",
            "below": self._num(self.alert.get("below")),
            "amount": "", "plan": "", "plan_left": "", "plan_reset": "",
            "quota": "", "quota_used": "", "quota_left": "", "quota_total": "", "quota_reset": "",
            "_isPeak": is_peak,
        }

    @staticmethod
    def _peak_now() -> bool:
        """峰谷判定（原版本地兜底规则：工作日 9-12 / 14-18 为高峰）。"""
        now = time.localtime()
        return now.tm_wday < 5 and (9 <= now.tm_hour < 12 or 14 <= now.tm_hour < 18)

    @staticmethod
    def peak_countdown() -> str:
        """距下一次峰/谷切换的倒计时（原版 {countdown}，HH:MM:SS）。"""
        now = time.localtime()
        hour = now.tm_hour
        if now.tm_wday >= 5:                       # 周末全天谷价
            return "00:00:00"
        target_hour = None
        for start, end in ((9, 12), (14, 18)):
            if start <= hour < end:
                target_hour = end
                break
        if target_hour is None:
            target_hour = 9 if hour < 9 else 9     # 睡前 → 次日 9 点
        stamp = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, target_hour, 0, 0, 0, 0, -1))
        if stamp <= time.time():
            stamp += 86400
        remain = max(0, int(stamp - time.time()))
        return "%02d:%02d:%02d" % (remain // 3600, (remain % 3600) // 60, remain % 60)

    @staticmethod
    def peak_label() -> str:
        """峰谷文案（原版按工作日 9-12 / 14-18 判高峰）。"""
        return "高峰时段" if WhalePet._peak_now() else "空闲时段"

    def show_modules(self, modules: list[dict], ms: int = QUOTE_TTL_MS) -> None:
        """按自定义模块渲染泡泡（走原版模块规则：字号档位 / 配色 / 行分组 / 图片 / 随机行）。"""
        image_dirs = [os.path.join(data.dsh_home(), "whale-bubble-imgs")]

        def render():
            balloon, content = card.render_bubble_modules(
                modules, self.assets, self.balloon_width, values=self.bubble_values(),
                split=True, image_dirs=image_dirs)
            x, y, tail = self.bubble_placement(balloon.width, balloon.height)
            if tail == "up":
                balloon, content = card.render_bubble_modules(
                    modules, self.assets, self.balloon_width, values=self.bubble_values(),
                    tail="up", split=True, image_dirs=image_dirs)
            if self.flip:
                balloon = balloon.transpose(Image.FLIP_LEFT_RIGHT)
                if self.snap.get("flipText"):
                    content = content.transpose(Image.FLIP_LEFT_RIGHT)
            return balloon, content, [], x, y

        balloon, content, links, x, y = render()
        self._pop_layers(balloon, content, ms, links, x, y, render=render)

    def _show_config_item(self, item: dict, ms: int = QUOTE_TTL_MS) -> bool:
        """执行配置里的一项：normal / random / custom / choice（并列步骤按权重抽）。"""
        kind = str((item or {}).get("kind") or "normal")
        if kind == "choice":
            options = [opt for opt in ((item or {}).get("options") or []) if isinstance(opt, dict)]
            if not options:
                return False
            total = sum(max(1, int(opt.get("w") or 1)) for opt in options)
            roll = random.random() * total
            for option in options:
                roll -= max(1, int(option.get("w") or 1))
                if roll < 0:
                    return self._show_config_item(option.get("item") or {}, ms)
            return self._show_config_item((options[-1].get("item") or {}), ms)
        if kind == "custom":
            modules = [m for m in ((item or {}).get("modules") or []) if isinstance(m, dict)]
            if not modules:
                return False
            self.show_modules(modules, ms)
            return True
        if kind == "random":
            self.show_random_lines(ms)
            return True
        self.show_bubble("balance", ms)
        return True

    def _advance_manual(self) -> None:
        """手动轮：按配置的 items 往后走一项；走完就收起，下次从第 1 项开始。"""
        items = self.bubble_items_cfg
        if not items:
            kinds = self.manual_kinds()
            if self.bubble_seq_idx >= len(kinds):
                self.bubble_seq_idx = 0
                self.bubble.hide()
                return
            kind = kinds[self.bubble_seq_idx]
            self.bubble_seq_idx += 1
            self.show_bubble(kind, QUOTE_TTL_MS)
            return
        if self.bubble_seq_idx >= len(items):
            self.bubble_seq_idx = 0
            self.bubble.hide()
            return
        item = items[self.bubble_seq_idx]
        self.bubble_seq_idx += 1
        if not self._show_config_item(item if isinstance(item, dict) else {}):
            self.bubble.hide()

    def _reset_manual_ttl(self) -> None:
        self._cancel_ttl()
        self.bubble_ttl_job = self.bubble.win.after(QUOTE_TTL_MS, self._manual_ttl)

    def _manual_ttl(self) -> None:
        self.bubble_ttl_job = None
        self.bubble_seq_idx = 0
        self.bubble.hide()

    def bubble_reset_ttl(self) -> None:
        self._reset_manual_ttl()

    def _pop_layers(self, balloon, content, ms: int, links, x: int, y: int,
                    on_ttl=None, render=None) -> None:
        """原版式弹出：气球鼓起来、文字按原版时序淡入；并布置停留计时。

        `render` 是"重新渲染当前气泡"的回调（拖动/翻转/缩放时用它同步）。
        """
        self._cancel_ttl()
        self.bubble_spec = {"render": render, "size": (balloon.width, balloon.height),
                            "tail": self.bubble_placement(balloon.width, balloon.height)[2]}
        self.bubble.show_layers(balloon, content, x, y, links, sync_text=self.sync_text)
        if ms and ms > 0:
            self.bubble_ttl_job = self.bubble.win.after(ms, on_ttl or self._manual_ttl)

    def _bubble_alive(self) -> bool:
        return bool(self.bubble.visible or self.bubble.opening)

    def _follow_bubble(self) -> None:
        """让气泡跟着挂件跑（拖动、贴边、改尺寸时调用）。"""
        spec = self.bubble_spec
        if not spec or not self._bubble_alive():
            return
        width, height = spec.get("size", (0, 0))
        if not width:
            return
        x, y, tail = self.bubble_placement(width, height)
        if tail != spec.get("tail"):
            self._refresh_bubble()          # 朝向要变（比如跑到顶部）→ 重画
            return
        self.bubble.win.geometry("+%d+%d" % (x, y))

    def _refresh_bubble(self) -> None:
        """按当前朝向/位置**重画**正在显示的气泡：镜像、贴顶倒挂、缩放、DPI 变化。"""
        spec = self.bubble_spec
        if not spec or not self._bubble_alive():
            return
        render = spec.get("render")
        if not render:
            self._follow_bubble()
            return
        try:
            balloon, content, links, x, y = render()
        except Exception as exc:
            self._log("气泡重画失败：%s" % exc)
            return
        spec["size"] = (balloon.width, balloon.height)
        spec["tail"] = self.bubble_placement(balloon.width, balloon.height)[2]
        self.bubble.update_layers(balloon, content, links)
        self.bubble.win.geometry("+%d+%d" % (x, y))

    def toggle_sync_text(self) -> None:
        self.sync_text = bool(self.var_sync_text.get())
        data.write_state({"syncText": self.sync_text})

    def _cancel_ttl(self) -> None:
        if self.bubble_ttl_job:
            try:
                self.bubble.win.after_cancel(self.bubble_ttl_job)
            except Exception:
                pass
            self.bubble_ttl_job = None

    def show_bubble(self, kind: str, ms: int = QUOTE_TTL_MS) -> None:
        if kind == "balance":
            # 原版默认内容：label "DeepSeek 余额" / amount 余额 / hint "今日已用 …"
            if self.balance and self.balance.get("ok"):
                amount = data.money(float(self.balance.get("total") or 0), self.currency())
                hint = "%s %s" % (self.usage_label(),
                                  data.money(data.today_usage(self.usage), self.currency()))
                if not self.balance.get("available", True):
                    hint = "账户不可用"
            elif self.balance:
                amount = "--"
                hint = str(self.balance.get("error") or "")[:14]
            else:
                amount = "…"
                hint = "加载中…"
                self.refresh_balance(bubble=False)
            slots = [{"t": "DeepSeek 余额", "s": "A"}, {"t": amount, "s": "B"}, {"t": hint, "s": "C"}]
            balloon, content, links, x, y = self._bubble_layers(slots)
            self._pop_layers(balloon, content, ms, links, x, y,
                             render=lambda: self._bubble_layers(slots))
        elif kind == "today":
            self.refresh_local()
            amount = data.money(data.today_usage(self.usage), self.currency())
            slots = [None, {"t": amount, "s": "B"}, {"t": "小鲸鱼记账", "s": "C"}]
            balloon, content, links, x, y = self._bubble_layers(slots)
            self._pop_layers(balloon, content, ms, links, x, y,
                             render=lambda: self._bubble_layers(slots))
        elif kind == "gif":
            self._show_gif_bubble(ms)
        else:
            self.show_random_lines(ms)

    def usage_label(self) -> str:
        """hint 行的前缀，原版是 state.usageLabel || '今日已用'。"""
        return "今日已用"

    def show_random_lines(self, ms: int = QUOTE_TTL_MS) -> None:
        """随机台词：原版 pickRandomLines 的权重分组 —— 抽到 gif 组就放动图。"""
        lines = presets.pick_random_lines()
        if isinstance(lines, dict) and lines.get("gif"):
            if not self._show_gif_bubble(ms):
                lines = [None, {"t": presets.pick_one(["gif 加载失败了...", "今天没有动图给你看~",
                                                       "呜呜 动图不见了..."]), "s": "A", "w": True}, None]
            else:
                return
        balloon, content, links, x, y = self._bubble_layers(lines)
        self._pop_layers(balloon, content, ms, links, x, y,
                         render=lambda: self._bubble_layers(lines))

    def _show_gif_bubble(self, ms: int) -> bool:
        frames = self.sprites.rua_frames(int(round(120 * self.dpi_scale)))
        if not frames:
            return False
        x, y, _tail = self.bubble_placement(frames[0][0].width, frames[0][0].height)
        self._cancel_ttl()
        self.bubble_spec = {"render": None, "size": (frames[0][0].width, frames[0][0].height),
                            "tail": _tail}
        self.bubble.show_frames(frames, x, y, ms, speed=self.gif_speed)
        self.bubble_ttl_job = self.bubble.win.after(ms, self._manual_ttl)
        return True

    # ---------------- 收尾 ----------------
    def quit(self) -> None:
        try:
            data.write_state({
                "pos": [self.root.winfo_x(), self.root.winfo_y()],
                "scale": self.scale,
            })
        except Exception:
            pass
        self.audio.stop_all()
        self.root.destroy()

    def diagnostics(self) -> dict:
        style = get_exstyle(self.hwnd)
        bubble_img = gfx.render_bubble(["余额 ¥2.19", "今日已用 ¥0.29"],
                                       width=self.balloon_width, ui_scale=self.dpi_scale)
        return {
            "ok": True,
            "python": sys.version.split()[0],
            "assets": self.assets,
            "dpi": {"awareness": self.dpi_aware, "dpi": self.dpi, "uiScale": round(self.dpi_scale, 3)},
            "sprite": {"path": self.sprites.base_path, "base": list(self.sprites.base_size),
                       "content": list(self.sprites.content_size), "window": [self.win_w, self.win_h],
                       "scale": self.scale, "imgScale": round(self.img_scale, 4)},
            "animation": {"frames": len(self.frame_table), "buildMs": getattr(self, "frame_build_ms", None),
                          "tickMs": TICK_MS, "param": round(self._anim_p(), 3),
                          "pRange": [FRAME_P_MIN, FRAME_P_MAX]},
            "ruaFrames": len(self.sprites.rua_frames()),
            "alert": {"on": self.alert.get("on"), "below": self.alert.get("below"),
                      "fired": self.alert_fired,
                      "customLines": bool(self.alert.get("lines"))},
            "snap": dict(self.snap),
            "flip": self.flip,
            "upsideDown": self.upside_down,
            "gifSpeed": self.gif_speed,
            "pressSpec": {"squish": "scaleY(%.2f) scaleX(%.2f)" % (1 - PRESS_SQUASH_Y, 1 + PRESS_SQUASH_X),
                          "ms": PRESS_MS, "bezier": list(PRESS_BEZIER),
                          "squashNow": round(self.squash, 3)},
            "hwnd": self.hwnd,
            "styles": {
                "toolwindow": bool(style & WS_EX_TOOLWINDOW),
                "layered": bool(style & WS_EX_LAYERED),
                "transparent(clickThrough)": bool(style & WS_EX_TRANSPARENT),
                "noactivate": bool(style & WS_EX_NOACTIVATE),
            },
            "transparentcolor": gfx.KEY_HEX,
            "bubble": [bubble_img.width, bubble_img.height],
            "audio": {
                "press": self.audio.resolve("Ya1.mp3"),
                "release": self.audio.resolve("Ya2.mp3"),
                "taskEnd": self.audio.resolve("task-end-a.wav"),
            },
            "data": {
                "credentials": bool(data.api_key()),
                "balance": self.balance,
                "todayUsage": data.today_usage(self.usage),
                "turnSeq": self.turn_seq,
                "size": self.cfg,
            },
            "autostart": autostart_enabled(),
            "state": data.read_state(),
        }


def _paste_preview(pet: "WhalePet", bubble_rgba: Image.Image, bx: int, by: int, target: str) -> dict:
    """把挂件窗口图与气泡/卡片按真实相对位置合到棋盘底上。"""
    pet_img = gfx.key_to_alpha(pet.window_image())
    px, py = pet.root.winfo_x(), pet.root.winfo_y()
    pad = 22
    left, top = min(px, bx), min(py, by)
    width = max(px + pet.win_w, bx + bubble_rgba.width) - left + pad * 2
    height = max(py + pet.win_h, by + bubble_rgba.height) - top + pad * 2
    board = gfx.checkerboard(width, height)
    board.alpha_composite(bubble_rgba, (bx - left + pad, by - top + pad))
    board.alpha_composite(pet_img, (px - left + pad, py - top + pad))
    board.convert("RGB").save(target)
    return {"path": target, "canvas": [width, height],
            "bubbleOffsetFromPet": [bx - px, by - py],
            "scaleFactors": [round(v, 4) for v in pet._scale_factors(pet._anim_p())]}


def write_snapshot(pet: "WhalePet", path: str) -> dict:
    """离屏合成预览：文本气泡 / 按压 / 余额预警卡片 / 每轮消耗卡片 / 镜像态。"""
    def target_for(tag: str) -> str:
        return path if not tag else os.path.splitext(path)[0] + tag + os.path.splitext(path)[1]

    results: dict = {}
    previous_flip = pet.flip
    previous_upside = pet.upside_down
    pet.flip = False          # 前四张按非镜像态出图，便于对比

    # 1) 常态：原版默认内容（label / amount / hint 三行）
    pet.squash = 0.0
    slots = [{"t": "DeepSeek 余额", "s": "A"},
             {"t": data.money(1.99), "s": "B"},
             {"t": "今日已用 %s" % data.money(0.43), "s": "C"}]
    balloon, content, links, bx, by = pet._bubble_layers(slots)
    results["preview"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by, target_for(""))

    # 1b) 随机台词（原版权重抽签：这里固定抽「好模型... ↓」这种 amount 样式，看字号自适应）
    quote_slots = [None, {"t": "好模型... ↓", "s": "B"}, None]
    balloon, content, links, bx, by = pet._bubble_layers(quote_slots)
    results["preview-quote"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                              target_for("-quote"))

    # 1c) 长句折行（原版 A 样式 + wrap）
    long_slots = [None, {"t": "不知道用户有什么用，先赶走吧~", "s": "A", "w": True}, None]
    balloon, content, links, bx, by = pet._bubble_layers(long_slots)
    results["preview-long"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                             target_for("-long"))

    # 2) 按到底（Q 弹）
    pet.squash = 1.0
    balloon, content, links, bx, by = pet._bubble_layers(["摸摸鲸鱼娘~"])
    results["preview-press"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                              target_for("-press"))
    pet.squash = 0.0

    # 3) 余额预警卡片（原版样式）
    balloon, content, links, bx, by = pet.alert_layers()
    results["preview-alert"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                              target_for("-alert"))
    results["preview-alert"]["links"] = links

    # 4) 每轮消耗卡片
    balloon, content, links, bx, by = pet.turn_cost_layers(0.2984, 1691118, "deepseek-flash")
    results["preview-turn"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                             target_for("-turn"))
    results["preview-turn"]["links"] = links

    # 5) 镜像态（越过翻转线）
    pet.flip = True
    balloon, content, links, bx, by = pet.alert_layers()
    results["preview-flip"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                             target_for("-flip"))
    pet.flip = previous_flip

    # 6) 弹出动画的三帧（气球 0.7 → 1.0，文字 0.36s 后淡入）
    pet.flip = False
    balloon, content, links, bx, by = pet.alert_layers()
    for tag, scale, fade in (("-pop1", 0.72, 0.0), ("-pop2", 0.90, 0.45), ("-pop3", 1.0, 1.0)):
        frame = pet.bubble._compose_layers(balloon, content, scale, fade)
        results["preview" + tag] = _paste_preview(pet, gfx.key_to_alpha(frame), bx, by, target_for(tag))
        # 6) 贴顶倒挂
        pet.flip = False
        pet.upside_down = True
        pet._build_frame_table()
        pet.draw(force=True)
        balloon, content, links, bx, by = pet.alert_layers()
        results["preview-upside"] = _paste_preview(pet, Image.alpha_composite(balloon, content), bx, by,
                                                   target_for("-upside"))
        results["preview-upside"]["tail"] = pet.bubble_placement(balloon.width, balloon.height)[2]
        pet.upside_down = previous_upside
        pet._build_frame_table()
        pet.draw(force=True)
    pet.flip = previous_flip
    return results


def find_assets() -> str:
    candidates = [
        os.environ.get("DSHW_ASSETS"),
        os.path.join(HERE, "assets"),
        os.path.join(HERE, "..", "assets"),
        os.path.join(HERE, "..", "..", "assets"),
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "DSniang1.png")):
            return os.path.abspath(path)
    raise RuntimeError("找不到 assets 目录（需要 DSniang1.png）")


def self_rect(window) -> tuple[int, int]:
    """窗口在**屏幕**上的绝对左上角（Toplevel 的 winfo_x 是相对父窗口的，不能用）。"""
    if _user32 is None:
        return (window.winfo_x(), window.winfo_y())
    try:
        hwnd = hwnd_of(window)
        rect = wt.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (int(rect.left), int(rect.top))
    except Exception:
        return (window.winfo_x(), window.winfo_y())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DSH 小鲸鱼桌面挂件（Python 版）")
    parser.add_argument("--selftest", action="store_true", help="无界面自检，打印 JSON 后退出")
    parser.add_argument("--snapshot", metavar="PNG", help="离屏合成一张预览图后退出")
    args = parser.parse_args(argv)

    awareness = enable_dpi_awareness()      # 必须在创建 Tk 之前声明，否则窗口会被系统拉伸
    root = tk.Tk()
    root.title("DSH 小鲸鱼桌面挂件")
    if args.selftest or args.snapshot:
        root.withdraw()

    pet = WhalePet(root)
    pet.dpi_aware = awareness

    if args.snapshot:
        root.update()
        print(json.dumps(write_snapshot(pet, args.snapshot), ensure_ascii=False, indent=2))
        root.destroy()
        return 0

    if args.selftest:
        deadline = time.time() + 1.5
        while time.time() < deadline:
            root.update()
            pet.tick_once()
            time.sleep(0.016)

        # 量一下"换一帧"的真实开销（强制每次都换图 = 最坏情况）
        rounds = 400
        started = time.perf_counter()
        for _ in range(rounds):
            pet.frame_index = -1
            pet.tick_once()
        per_frame_ms = (time.perf_counter() - started) * 1000.0 / rounds

        info = pet.diagnostics()
        info["measuredMsPerFrame"] = round(per_frame_ms, 3)
        info["headroomAt60fps"] = "%d%%" % round((1.0 - per_frame_ms / (1000.0 / 60.0)) * 100)

        # 卡片与预警链路自检（不放音，避免打扰）
        pet.sound_on = False
        balloon, content, alert_links = pet._render_modules(
            pet.alert_modules(), {"below": pet._num(pet.alert.get("below"))})
        alert_img = Image.alpha_composite(balloon, content)
        turn_modules, turn_values = pet.turn_cost_modules(0.2984, 1691118, "deepseek-flash")
        balloon2, content2, turn_links = pet._render_modules(turn_modules, turn_values)
        turn_img = Image.alpha_composite(balloon2, content2)
        info["cards"] = {
            "alert": {"size": [alert_img.width, alert_img.height], "links": alert_links},
            "turnCost": {"size": [turn_img.width, turn_img.height], "links": turn_links},
        }
        # 弹出动画：三帧的尺寸/缩放（原版是 scale(.7) → 1，文字延迟 0.36s）
        frames = []
        for scale, fade in ((0.72, 0.0), (0.90, 0.45), (1.0, 1.0)):
            frame = pet.bubble._compose_layers(balloon, content, scale, fade)
            frames.append({"scale": scale, "textFade": fade,
                           "keyPixels": frame.convert("RGB").point(
                               lambda v: 0 if v < 250 else 255).getbbox() is not None})
        info["popFrames"] = frames

        # 按压回弹曲线：原版 cubic-bezier(.34,1.56,.64,1)，中途会冲过 1（过冲）
        curve = []
        for u in (0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
            eased = bezier_y(*PRESS_BEZIER, u)
            sx, sy = pet._scale_factors(-eased)
            curve.append({"u": u, "eased": round(eased, 3), "scaleX": round(sx, 3), "scaleY": round(sy, 3)})
        info["pressCurve"] = curve

        # 图片台词：GIF 自带帧时长是否读到（速度倍率在此之上乘）
        rua = pet.sprites.rua_frames(int(round(120 * pet.dpi_scale)))
        info["gif"] = {"frames": len(rua), "speed": pet.gif_speed,
                       "durationsMs": [ms for _img, ms in rua[:8]]}
        pet.balance = {"ok": True, "total": 1.0, "currency": "CNY", "available": True}
        pet.alert["on"] = True
        pet.alert_fired = False
        pet._check_alert()
        first = pet.alert_fired
        queued = len(pet.sys_queue) + (1 if pet.sys_current else 0)
        pet._check_alert()          # 第二次不应重复触发
        info["alertTrigger"] = {"firedOnce": first, "queued": queued,
                                "secondCallStillFired": pet.alert_fired}
        pet.balance = {"ok": True, "total": 99.0, "currency": "CNY", "available": True}
        pet._check_alert()
        info["alertTrigger"]["rearmedAboveThreshold"] = not pet.alert_fired
        # 队列优先级：预算(1) 应排在预警(2)/消耗(3) 之前
        pet.sys_queue = []
        pet.push_system_bubble("cost", BUBBLE_RANK_COST, pet.alert_layers, 1000)
        pet.push_system_bubble("budget", BUBBLE_RANK_BUDGET, pet.alert_layers, 1000)
        pet.push_system_bubble("alert", BUBBLE_RANK_ALERT, pet.alert_layers, 1000)
        pet.push_system_bubble("cost", BUBBLE_RANK_COST, pet.alert_layers, 1000)
        info["queueOrder"] = [it["kind"] for it in pet.sys_queue]
        pet.sys_queue = []
        pet.bubble.hide(animate=False)

        # ① 拖动跟随：气泡窗口应跟着挂件一起位移
        #   注意：根窗口 withdrawn 时 Tk 不更新 winfo_x/y，必须短暂显示才能测准
        #   （贴屏幕边缘时气泡会被工作区边界钳住，所以先挪到中间）
        root.deiconify()
        root.update()
        area_left, area_top, area_right, area_bottom = pet.screen_work_area()
        pet.root.geometry("+%d+%d" % (int((area_left + area_right) / 2 - pet.win_w / 2),
                                      int((area_top + area_bottom) / 2 - pet.win_h / 2)))
        root.update()
        pet.apply_snap_and_flip(persist=False)
        root.update()
        pet.show_short("跟随测试", 4000)
        root.update()
        before = self_rect(pet.bubble.win)
        pet_before = self_rect(pet.root)
        pet.root.geometry("+%d+%d" % (pet_before[0] - 64, pet_before[1] - 37))
        root.update()
        pet._follow_bubble()
        root.update()
        after = self_rect(pet.bubble.win)
        pet_after = self_rect(pet.root)
        info["bubbleFollow"] = {
            "petMoved": [pet_after[0] - pet_before[0], pet_after[1] - pet_before[1]],
            "bubbleMoved": [after[0] - before[0], after[1] - before[1]],
            "followed": (after[0] - before[0]) == (pet_after[0] - pet_before[0])
                        and (after[1] - before[1]) == (pet_after[1] - pet_before[1]),
        }
        pet.bubble.hide(animate=False)
        root.withdraw()

        # ② 翻转同步：镜像后气泡层应当正好是原图的左右翻转
        pet.upside_down = False
        pet.flip = False
        plain, _c1, _l1, _x1, _y1 = pet._bubble_layers(["翻转测试"])
        pet.flip = True
        mirrored, _c2, _l2, _x2, _y2 = pet._bubble_layers(["翻转测试"])
        pet.flip = False
        back = mirrored.transpose(Image.FLIP_LEFT_RIGHT).convert("RGB")
        info["bubbleFlip"] = {
            "balloonChanged": plain.tobytes() != mirrored.tobytes(),
            "mirrorIsExact": ImageChops.difference(plain.convert("RGB"), back).getbbox() is None,
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        root.destroy()
        return 0

    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
