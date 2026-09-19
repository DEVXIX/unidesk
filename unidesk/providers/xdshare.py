"""What a shared screen can be: the whole desktop, or one window.

Sharing a rectangle of the screen is the easy version and the wrong one. The
rectangle a window occupies is not the window: anything sitting on top of it -
a chat, a notification, the call page itself - is inside that rectangle and
goes out with it. PrintWindow asks the window to draw itself instead, so what
leaves the machine is that window and only that window, whatever is in front of
it.

PW_RENDERFULLCONTENT is what makes it work on modern windows; without it a
window drawn by the compositor (which is most of them) comes back black.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .. import desktop

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0

# Declared rather than left to ctypes' defaults. An undeclared HWND or HDC is
# taken for a C int, which on 64-bit silently truncates every handle to its
# bottom half - the calls then fail in ways that look like the window is gone.
for _name, _res, _args in [
    ("PrintWindow", wintypes.BOOL, [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
    ("GetWindowDC", wintypes.HDC, [wintypes.HWND]),
    ("ReleaseDC", ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
    ("GetWindowTextLengthW", ctypes.c_int, [wintypes.HWND]),
    ("GetWindowTextW", ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
    ("GetWindowLongPtrW", ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int]),
    ("GetWindowRect", wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
    ("IsWindowVisible", wintypes.BOOL, [wintypes.HWND]),
    ("IsIconic", wintypes.BOOL, [wintypes.HWND]),
    ("EnumWindows", wintypes.BOOL, [desktop.EnumWindowsProc, wintypes.LPARAM]),
]:
    _fn = getattr(user32, _name)
    _fn.restype, _fn.argtypes = _res, _args

for _name, _res, _args in [
    ("CreateCompatibleDC", wintypes.HDC, [wintypes.HDC]),
    ("CreateCompatibleBitmap", wintypes.HBITMAP, [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
    ("SelectObject", wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
    ("DeleteObject", wintypes.BOOL, [wintypes.HGDIOBJ]),
    ("DeleteDC", wintypes.BOOL, [wintypes.HDC]),
    ("GetDIBits", ctypes.c_int,
     [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]),
]:
    _fn = getattr(gdi32, _name)
    _fn.restype, _fn.argtypes = _res, _args


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def windows() -> list[dict]:
    """Everything worth offering to share: visible, titled, ordinary windows."""
    import os

    found: list[dict] = []
    own = os.getpid()

    def visit(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            style = user32.GetWindowLongPtrW(hwnd, desktop.GWL_STYLE)
            ex = user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
            # A window somebody can share is one they can see and point at: it
            # has a title bar, it is not a tool palette, and it is not one of
            # the shell's own invisible helpers.
            if (style & desktop.WS_CAPTION) != desktop.WS_CAPTION:
                return True
            if ex & desktop.WS_EX_TOOLWINDOW or desktop._cloaked(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title:
                return True
            pid = desktop._pid(hwnd)
            if own and pid == own:
                return True
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if rect.right - rect.left < 120 or rect.bottom - rect.top < 80:
                return True
            found.append({"id": str(int(hwnd)), "name": title, "app": desktop.process_name(pid)})
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(desktop.EnumWindowsProc(visit), 0)
    except Exception:
        pass
    return found


def window_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (0, 0)
    return (rect.right - rect.left, rect.bottom - rect.top)


def grab_window(hwnd: int) -> tuple[bytes, int, int] | None:
    """One window, drawn by itself, as BGRA bytes.

    Returns None when the window has gone, which is the ordinary end of a share
    rather than an error: somebody closed what they were showing.
    """
    width, height = window_size(hwnd)
    if width <= 0 or height <= 0:
        return None

    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        return None
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    try:
        gdi32.SelectObject(memory_dc, bitmap)
        # Ask the window to draw. A window that refuses still leaves whatever
        # the compositor has, which is better than a black rectangle.
        user32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT)

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        # Negative, so the rows come back top-down the way every other image
        # format in this program expects them.
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0

        buffer = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)
        if not copied:
            return None
        return (buffer.raw, width, height)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
