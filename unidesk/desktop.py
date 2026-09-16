"""Win32 glue: keep widget windows on the desktop layer, and notice when a
fullscreen app (a game, a video) covers the screen so unidesk can go idle."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
MONITOR_DEFAULTTONEAREST = 2

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]

_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE


def pin_to_desktop(hwnd: int):
    """Owned by the desktop (so it sits just above the wallpaper), no focus, no Alt+Tab."""
    h = wintypes.HWND(hwnd)
    ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(h, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    progman = user32.FindWindowW("Progman", None)
    if progman:
        user32.SetWindowLongPtrW(h, GWLP_HWNDPARENT, progman)
    send_to_back(hwnd)


def set_activatable(hwnd: int, on: bool):
    h = wintypes.HWND(hwnd)
    ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
    ex = ex & ~WS_EX_NOACTIVATE if on else ex | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(h, GWL_EXSTYLE, ex)


def send_to_back(hwnd: int):
    h = wintypes.HWND(hwnd)
    user32.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0, _FLAGS)
    user32.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, _FLAGS)


def bring_to_front(hwnd: int):
    user32.SetWindowPos(wintypes.HWND(hwnd), HWND_TOPMOST, 0, 0, 0, 0, _FLAGS)


_DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def fullscreen_app_active(own_pid: int) -> bool:
    """True when the foreground window (not ours, not the desktop) covers its whole monitor."""
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    if pid.value == own_pid:
        return False
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, name, 64)
    if name.value in _DESKTOP_CLASSES:
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(fg, ctypes.byref(rect))
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST), ctypes.byref(info)):
        return False
    m = info.rcMonitor
    return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom
