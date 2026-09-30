# -*- coding: utf-8 -*-
"""直接抓某个窗口自身的渲染像素（PrintWindow + PW_RENDERFULLCONTENT）。

用途：分层/透明窗口不会出现在 BitBlt 的屏幕截图中，但可以被 PrintWindow 抓到 ——
这是验证"挂件到底画没画出来"的可靠办法。

用法： python capture_window.py <窗口标题> <输出png>
"""
import ctypes
import ctypes.wintypes as wt
import sys

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


def grab(hwnd: int, out: str) -> tuple[int, int]:
    rc = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    width, height = rc.right - rc.left, rc.bottom - rc.top

    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bmp)

    # 2 = PW_RENDERFULLCONTENT（能抓分层/合成窗口）
    user32.PrintWindow(hwnd, mem, 2)

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height       # 负数 = 自上而下
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(header), 0)

    image = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    image.convert("RGB").save(out)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return width, height


def find_by_title(title: str) -> int:
    """找标题匹配的可见窗口；有多个时取面积最大的（气泡窗口与主窗口同名）。"""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def callback(h, _l):
        text = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, text, 255)
        if title in text.value and user32.IsWindowVisible(h):
            rc = wt.RECT()
            user32.GetWindowRect(h, ctypes.byref(rc))
            found.append(((rc.right - rc.left) * (rc.bottom - rc.top), h))
        return True

    user32.EnumWindows(callback, 0)
    found.sort(reverse=True)
    return found[0][1] if found else 0


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "DSH 小鲸鱼桌面挂件"
    out = sys.argv[2] if len(sys.argv) > 2 else "window.png"
    handle = find_by_title(title)
    if not handle:
        print("找不到窗口：%s" % title)
        sys.exit(1)
    print("hwnd", handle, "size", grab(handle, out), "->", out)
