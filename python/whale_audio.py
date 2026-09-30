# -*- coding: utf-8 -*-
"""音频层：不装任何第三方库，用 Windows 自带能力放音。

  .mp3 / .wav  → MCI（winmm.mciSendString），支持音量、可并发多路
  .wav         → winsound 兜底

仓库 assets/ 里给的音效是 mp3（Ya1/Ya2/D1/D2）和 wav（task-end-a / minecraft-exp-orb），
两种都要能放，所以主路径是 MCI。
"""
from __future__ import annotations

import ctypes
import os
import threading
import time

try:
    import winsound
except Exception:  # 非 Windows
    winsound = None

_winmm = getattr(ctypes, "windll", None)
_winmm = _winmm.winmm if _winmm is not None else None

# MCI 返回码
MCI_OK = 0


class Audio:
    """音效播放器：按文件名播放 assets/ 下的音频。"""

    def __init__(self, assets_dir: str, log=None):
        self.assets_dir = assets_dir
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._counter = 0
        self._aliases: list[str] = []

    # ---------------- MCI 底层 ----------------
    def _mci(self, command: str) -> int:
        if _winmm is None:
            return 1
        buf = ctypes.create_unicode_buffer(256)
        try:
            return int(_winmm.mciSendStringW(ctypes.c_wchar_p(command), buf, 255, None))
        except Exception:
            return 1

    def _mci_status(self, alias: str) -> str:
        if _winmm is None:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        try:
            code = int(_winmm.mciSendStringW(ctypes.c_wchar_p("status %s mode" % alias), buf, 255, None))
            return buf.value if code == MCI_OK else ""
        except Exception:
            return ""

    def _mci_close_later(self, alias: str, timeout: float = 30.0) -> None:
        """等这一路放完再 close（MCI 不 close 会一直占着设备）。"""

        def waiter():
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._mci_status(alias) != "playing":
                    break
                time.sleep(0.2)
            self._mci("close %s" % alias)
            with self._lock:
                if alias in self._aliases:
                    self._aliases.remove(alias)

        threading.Thread(target=waiter, name="dshw-mci-close", daemon=True).start()

    # ---------------- 对外 ----------------
    def resolve(self, name: str) -> str | None:
        """把音效名解析成 assets/ 下的绝对路径（支持带或不带扩展名）。"""
        if not name:
            return None
        candidate = os.path.join(self.assets_dir, name)
        if os.path.isfile(candidate):
            return candidate
        for ext in (".mp3", ".wav"):
            if os.path.isfile(candidate + ext):
                return candidate + ext
        return None

    def play(self, name: str, volume: float = 0.7) -> bool:
        """播放音效；找不到文件/放不出来都安静失败（挂件不能因为没声音就报错）。"""
        path = self.resolve(name)
        if not path:
            self.log("音效文件不存在：%s" % name)
            return False
        if volume is not None and volume <= 0:
            return False

        ext = os.path.splitext(path)[1].lower()
        vol = int(max(0.0, min(1.0, float(volume if volume is not None else 0.7))) * 1000)

        if _winmm is not None:
            with self._lock:
                self._counter += 1
                alias = "dshw%d" % self._counter
            # 路径用短引号包住；type 由 MCI 自己嗅探（mpegvideo 能吃 mp3）
            open_cmd = 'open "%s" alias %s' % (path, alias)
            if self._mci(open_cmd) == MCI_OK:
                if vol > 0:
                    self._mci("setaudio %s volume to %d" % (alias, vol))
                if self._mci("play %s" % alias) == MCI_OK:
                    with self._lock:
                        self._aliases.append(alias)
                    self._mci_close_later(alias)
                    return True
                self._mci("close %s" % alias)

        # 兜底：wav 用 winsound（无音量控制）
        if winsound is not None and ext == ".wav":
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return True
            except Exception as exc:
                self.log("winsound 播放失败：%s" % exc)
        return False

    def stop_all(self) -> None:
        with self._lock:
            aliases = list(self._aliases)
            self._aliases.clear()
        for alias in aliases:
            self._mci("stop %s" % alias)
            self._mci("close %s" % alias)
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
