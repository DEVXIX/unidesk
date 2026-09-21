"""Win32 plumbing for the dock: app windows, icons, focus, shortcuts, the
real taskbar's auto-hide state and appbar space reservation. ctypes only."""
from __future__ import annotations

import ctypes
import hashlib
import os
import uuid
from ctypes import wintypes
from pathlib import Path

from ..desktop import MONITORINFOEXW, MONITOR_DEFAULTTONEAREST, window_monitor

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
gdi32 = ctypes.WinDLL("gdi32")
ole32 = ctypes.WinDLL("ole32")
version = ctypes.WinDLL("version")

HWND = wintypes.HWND
LONG_PTR = ctypes.c_ssize_t

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x80, 0x40000, 0x08000000
GW_OWNER = 4
SW_RESTORE, SW_MINIMIZE = 9, 6
# Minimised without taking the focus with it: minimising a dozen windows
# with SW_MINIMIZE hands the focus to each next one in turn on the way down.
SW_SHOWMINNOACTIVE = 7
WM_CLOSE = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DWMWA_CLOAKED = 14

for name, res, args in [
    ("EnumWindows", wintypes.BOOL, [ctypes.c_void_p, wintypes.LPARAM]),
    ("EnumChildWindows", wintypes.BOOL, [HWND, ctypes.c_void_p, wintypes.LPARAM]),
    ("IsWindowVisible", wintypes.BOOL, [HWND]),
    ("IsIconic", wintypes.BOOL, [HWND]),
    ("IsWindow", wintypes.BOOL, [HWND]),
    ("GetWindow", HWND, [HWND, wintypes.UINT]),
    ("GetWindowLongPtrW", LONG_PTR, [HWND, ctypes.c_int]),
    ("SetWindowLongPtrW", LONG_PTR, [HWND, ctypes.c_int, LONG_PTR]),
    ("GetWindowTextLengthW", ctypes.c_int, [HWND]),
    ("GetWindowTextW", ctypes.c_int, [HWND, wintypes.LPWSTR, ctypes.c_int]),
    ("GetClassNameW", ctypes.c_int, [HWND, wintypes.LPWSTR, ctypes.c_int]),
    ("GetWindowThreadProcessId", wintypes.DWORD, [HWND, ctypes.POINTER(wintypes.DWORD)]),
    ("GetForegroundWindow", HWND, []),
    ("SetForegroundWindow", wintypes.BOOL, [HWND]),
    ("BringWindowToTop", wintypes.BOOL, [HWND]),
    ("ShowWindow", wintypes.BOOL, [HWND, ctypes.c_int]),
    ("PostMessageW", wintypes.BOOL, [HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
    ("AttachThreadInput", wintypes.BOOL, [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]),
    ("FindWindowW", HWND, [wintypes.LPCWSTR, wintypes.LPCWSTR]),
    ("FindWindowExW", HWND, [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]),
    ("MonitorFromWindow", wintypes.HMONITOR, [HWND, wintypes.DWORD]),
    ("GetMonitorInfoW", wintypes.BOOL, [wintypes.HMONITOR, ctypes.c_void_p]),
    ("GetKeyboardLayout", wintypes.HKL, [wintypes.DWORD]),
    ("keybd_event", None, [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p]),
    ("SetWindowPos", wintypes.BOOL, [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]),
    ("AllowSetForegroundWindow", wintypes.BOOL, [wintypes.DWORD]),
]:
    fn = getattr(user32, name)
    fn.restype, fn.argtypes = res, args

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetApplicationUserModelId.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_uint32), wintypes.LPWSTR]
kernel32.GetApplicationUserModelId.restype = ctypes.c_long
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
dwmapi.DwmGetWindowAttribute.argtypes = [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.UINT]

EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)


# ---- windows ---------------------------------------------------------------------

def _text(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, buf, 128)
    return buf.value


def _pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _cloaked(hwnd) -> bool:
    value = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


def process_info(pid: int) -> tuple[str, str]:
    """(exe path, AppUserModelId or '') for a process."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "", ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        exe = buf.value if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else ""
        length = ctypes.c_uint32(512)
        abuf = ctypes.create_unicode_buffer(512)
        aumid = abuf.value if kernel32.GetApplicationUserModelId(handle, ctypes.byref(length), abuf) == 0 else ""
        return exe, aumid
    finally:
        kernel32.CloseHandle(handle)


def _uwp_child_pid(hwnd, host_pid: int) -> int:
    """ApplicationFrameHost wraps UWP apps; the real app owns a child CoreWindow."""
    found = []

    def cb(child, _):
        pid = _pid(child)
        if pid != host_pid:
            found.append(pid)
            return False
        return True

    user32.EnumChildWindows(hwnd, EnumProc(cb), 0)
    return found[0] if found else 0


_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"}


def app_windows(own_pid: int) -> list[dict]:
    """Windows that belong on a taskbar, front-most first."""
    out = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
            return True
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
            return True
        cls = _class(hwnd)
        if cls in _SKIP_CLASSES or _cloaked(hwnd):
            return True
        title = _text(hwnd)
        if not title:
            return True
        pid = _pid(hwnd)
        if pid == own_pid:
            return True
        if cls == "ApplicationFrameWindow":
            real = _uwp_child_pid(hwnd, pid)
            if not real:
                return True
            pid = real
        exe, aumid = process_info(pid)
        if not exe:
            return True
        out.append({"hwnd": int(hwnd), "title": title, "exe": exe, "aumid": aumid, "cls": cls,
                    "minimized": bool(user32.IsIconic(hwnd)), "monitor": window_monitor(hwnd)})
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def foreground() -> int:
    return int(user32.GetForegroundWindow() or 0)


user32.SwitchToThisWindow.argtypes = [HWND, wintypes.BOOL]
user32.SwitchToThisWindow.restype = None


def activate(hwnd: int):
    h = HWND(hwnd)
    if user32.IsIconic(h):
        user32.ShowWindow(h, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    try:
        if not user32.SetForegroundWindow(h):
            tap(0x12)  # a harmless Alt tap unlocks SetForegroundWindow
            user32.SetForegroundWindow(h)
        user32.BringWindowToTop(h)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)

    # Anything running as administrator sits above us, and Windows will not
    # let a program that is not elevated reach into one that is: attaching to
    # its input queue is refused, and the messages that bring a window forward
    # are dropped on the way. Clicking such a window on the dock did nothing
    # at all, and the only way to it was Alt+Tab.
    #
    # SwitchToThisWindow is what Alt+Tab itself uses, and it is handled by the
    # window manager rather than sent to the window - so it crosses that line.
    # Tried only when the ordinary route has already failed, because it also
    # ignores the animation settings and is abrupt when it is not needed.
    if user32.GetForegroundWindow() != hwnd:
        user32.SwitchToThisWindow(h, True)


def minimize(hwnd: int):
    user32.ShowWindow(HWND(hwnd), SW_MINIMIZE)


def minimize_quietly(hwnd: int):
    user32.ShowWindow(HWND(hwnd), SW_SHOWMINNOACTIVE)


def restore(hwnd: int):
    """Back to how it was before it was minimised - maximised if it was."""
    user32.ShowWindow(HWND(hwnd), SW_RESTORE)


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(HWND(hwnd)))


def exists(hwnd: int) -> bool:
    return bool(user32.IsWindow(HWND(hwnd)))


def close(hwnd: int):
    user32.PostMessageW(HWND(hwnd), WM_CLOSE, 0, 0)


def set_noactivate(hwnd: int):
    h = HWND(hwnd)
    ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(h, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def keep_on_top(hwnd: int):
    user32.SetWindowPos(HWND(hwnd), HWND(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)


# ---- keyboard shortcuts ------------------------------------------------------------

KEYUP = 0x2
VK_LWIN, VK_MENU = 0x5B, 0x12


def tap(*keys: int):
    """Press keys in order, release in reverse (e.g. tap(VK_LWIN, ord('S')))."""
    for k in keys:
        user32.keybd_event(k, 0, 0, None)
    for k in reversed(keys):
        user32.keybd_event(k, 0, KEYUP, None)


def keyboard_language() -> str:
    fg = user32.GetForegroundWindow()
    thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    lang = (user32.GetKeyboardLayout(thread) or 0) & 0xFFFF
    buf = ctypes.create_unicode_buffer(16)
    # LOCALE_SISO639LANGNAME2 (0x67): "eng", "ara", ...
    if kernel32.GetLocaleInfoW(lang, 0x67, buf, 16):
        return buf.value.upper()
    return ""


# ---- appbar + the real taskbar -----------------------------------------------------

class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", LONG_PTR)]


shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
shell32.SHAppBarMessage.restype = ctypes.c_size_t
ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS, ABM_GETSTATE, ABM_SETSTATE = 0, 1, 2, 3, 4, 10
ABE_BOTTOM, ABS_AUTOHIDE, ABS_ALWAYSONTOP = 3, 1, 2


def _abd(hwnd=None) -> APPBARDATA:
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = HWND(hwnd) if hwnd else None
    return abd


def reserve_bottom(hwnd: int, height: int):
    """Register as an appbar on the dock's monitor so maximised windows stop
    above the dock. Only what the (hidden) Windows taskbar doesn't already keep
    free is added, so windows don't stop a taskbar's height short of the dock."""
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    hmon = user32.MonitorFromWindow(HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    if not hmon or not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return
    m = info.rcMonitor
    abd = _abd(hwnd)
    abd.uCallbackMessage = 0x0400 + 0x2A
    shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
    abd.uEdge = ABE_BOTTOM
    abd.rc = wintypes.RECT(m.left, m.bottom - height, m.right, m.bottom)
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    extra = height - (m.bottom - abd.rc.bottom)  # QUERYPOS moved us above what others reserve
    if extra <= 0:
        release_reservation(hwnd)
        return
    abd.rc.top = abd.rc.bottom - extra
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))


def release_reservation(hwnd: int):
    shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(_abd(hwnd)))


def taskbar_autohide() -> bool:
    return bool(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(_abd())) & ABS_AUTOHIDE)


def set_taskbar_autohide(on: bool):
    abd = _abd(user32.FindWindowW("Shell_TrayWnd", None))
    state = shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd))
    abd.lParam = (state | ABS_AUTOHIDE) if on else (state & ~ABS_AUTOHIDE)
    shell32.SHAppBarMessage(ABM_SETSTATE, ctypes.byref(abd))


# ---- names ---------------------------------------------------------------------------

version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]


def file_description(exe: str) -> str:
    size = version.GetFileVersionInfoSizeW(exe, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(exe, 0, size, data):
        return ""
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(data, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(length)) or not length.value:
        return ""
    lang, codepage = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint16 * 2)).contents
    for key in ("FileDescription", "ProductName"):
        query = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{key}"
        if version.VerQueryValueW(data, query, ctypes.byref(ptr), ctypes.byref(length)) and length.value > 1:
            text = ctypes.wstring_at(ptr, length.value - 1).strip()
            if text:
                return text
    return ""


# ---- icons (IShellItemImageFactory) --------------------------------------------------

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str):
        u = uuid.UUID(text)
        g = cls()
        ctypes.memmove(ctypes.byref(g), u.bytes_le, 16)
        return g


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD), ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


IID_IShellItemImageFactory = GUID.of("bcc18b79-ba16-442f-80c4-8a59c30c463b")
IID_IShellItem = GUID.of("43826d1e-e718-42ee-bc55-a1e261c37bfe")
shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [HWND]
user32.ReleaseDC.argtypes = [HWND, wintypes.HDC]
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


def _vcall(obj: ctypes.c_void_p, index: int, restype, argtypes, *args):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
    return fn(obj, *args)


def _release(obj):
    if obj:
        _vcall(obj, 2, wintypes.ULONG, [])


def com_init():
    ole32.CoInitializeEx(None, 0x2)  # apartment threaded; harmless if already initialised


def shell_display_name(parsing: str) -> str:
    item = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(parsing, None, ctypes.byref(IID_IShellItem), ctypes.byref(item)) != 0:
        return ""
    try:
        name = ctypes.c_wchar_p()
        # IShellItem::GetDisplayName(SIGDN_NORMALDISPLAY = 0)
        if _vcall(item, 5, ctypes.c_long, [ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p)], 0, ctypes.byref(name)) != 0:
            return ""
        text = name.value or ""
        ole32.CoTaskMemFree(name)
        return text
    finally:
        _release(item)


def icon_png(parsing: str, size: int, cache: Path) -> str:
    """Render the shell icon of a file path or shell:AppsFolder\\AUMID to a cached PNG; returns its path or ''."""
    from PySide6.QtGui import QImage

    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{hashlib.sha1(f'{parsing}|{size}'.encode()).hexdigest()[:16]}.png"
    if out.exists():
        return str(out)
    factory = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(parsing, None, ctypes.byref(IID_IShellItemImageFactory), ctypes.byref(factory)) != 0:
        return ""
    hbm = wintypes.HBITMAP()
    try:
        # GetImage(SIZE, SIIGBF_BIGGERSIZEOK | SIIGBF_ICONONLY, HBITMAP*)
        hr = _vcall(factory, 3, ctypes.c_long, [SIZE, ctypes.c_int, ctypes.POINTER(wintypes.HBITMAP)], SIZE(size, size), 0x1 | 0x4, ctypes.byref(hbm))
        if hr != 0 or not hbm:
            return ""
        bm = BITMAP()
        gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
        buf = ctypes.create_string_buffer(w * h * 4)
        dc = user32.GetDC(None)
        gdi32.GetDIBits(dc, hbm, 0, h, buf, ctypes.byref(header), 0)
        user32.ReleaseDC(None, dc)
        image = QImage(buf.raw, w, h, QImage.Format.Format_ARGB32_Premultiplied).copy()
        if image.isNull() or not any(buf.raw[3::4]):
            # Some icons come back without alpha; treat as opaque.
            image = QImage(buf.raw, w, h, QImage.Format.Format_RGB32).copy()
        image.save(str(out))
        return str(out)
    finally:
        if hbm:
            gdi32.DeleteObject(hbm)
        _release(factory)


# ---- ghosting the real taskbar -------------------------------------------------------
# Hidden taskbars stop exposing their buttons (and the badge text we read from
# them), so instead of hiding it we keep it "shown" but fully transparent and
# click-through. Explorer can reset this (e.g. when it restarts), so the dock
# re-applies it periodically.

WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
LWA_ALPHA = 0x2
user32.SetLayeredWindowAttributes.argtypes = [HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL


def main_tray() -> int:
    return int(user32.FindWindowW("Shell_TrayWnd", None) or 0)


def _trays(secondary: bool = True) -> list:
    """The main taskbar, and the ones on other monitors."""
    trays = []
    main = user32.FindWindowW("Shell_TrayWnd", None)
    if main:
        trays.append(main)
    other = user32.FindWindowExW(None, None, "Shell_SecondaryTrayWnd", None) if secondary else None
    while other:
        trays.append(other)
        other = user32.FindWindowExW(None, other, "Shell_SecondaryTrayWnd", None)
    return trays


def _set_ghost(tray, on: bool):
    ex = user32.GetWindowLongPtrW(tray, GWL_EXSTYLE)
    if on:
        user32.SetWindowLongPtrW(tray, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        user32.SetLayeredWindowAttributes(tray, 0, 0, LWA_ALPHA)
    else:
        user32.SetLayeredWindowAttributes(tray, 0, 255, LWA_ALPHA)
        user32.SetWindowLongPtrW(tray, GWL_EXSTYLE, ex & ~(WS_EX_LAYERED | WS_EX_TRANSPARENT))
    user32.ShowWindow(tray, 8)  # SW_SHOWNA


def ghost_taskbars(main: bool, secondary: bool):
    """Ghost (or give back) the main taskbar and the other monitors' ones,
    touching only those not already in the wanted state."""
    first = main_tray()
    for tray in _trays():
        want = main if int(tray) == first else secondary
        if bool(user32.GetWindowLongPtrW(tray, GWL_EXSTYLE) & WS_EX_TRANSPARENT) != want:
            _set_ghost(tray, want)


def ghost_taskbar(on: bool):
    """Every taskbar at once (used by --restore-taskbar)."""
    for tray in _trays():
        _set_ghost(tray, on)


# ---- badges (read from the real taskbar through UI Automation) -----------------------

class BadgeReader:
    """Reads each taskbar button's badge text ("2 notifications") via UIA.
    Use from one background thread only (COM apartment)."""

    def __init__(self):
        import comtypes
        import comtypes.client

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass  # this thread already has a COM apartment
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        self._uia_mod = UIA
        self._uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        self._button_condition = self._uia.CreatePropertyCondition(UIA.UIA_ClassNamePropertyId, "Taskbar.TaskListButtonAutomationPeer")

    def read(self) -> list[dict]:
        """[{appid, name, count}] for buttons that carry a badge. count -1 = a dot without a number."""
        import re

        UIA = self._uia_mod
        out = []
        for tray in _trays(secondary=False):  # the other taskbars show the same buttons
            try:
                buttons = self._uia.ElementFromHandle(tray).FindAll(UIA.TreeScope_Descendants, self._button_condition)
            except Exception:
                continue
            for i in range(buttons.Length):
                b = buttons.GetElement(i)
                try:
                    help_text = b.GetCurrentPropertyValue(UIA.UIA_HelpTextPropertyId) or ""
                except Exception:
                    continue
                if not help_text:
                    continue
                name = (b.CurrentName or "").split(" - ")[0].replace(" pinned", "").strip()
                appid = (b.CurrentAutomationId or "").removeprefix("Appid: ").strip()
                number = re.search(r"\d+", help_text)
                out.append({"appid": appid, "name": name, "count": int(number.group(0)) if number else -1})
        return out


# ---- live window previews (DWM thumbnails) ------------------------------------------

class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("rcDestination", wintypes.RECT), ("rcSource", wintypes.RECT),
                ("opacity", ctypes.c_ubyte), ("fVisible", wintypes.BOOL), ("fSourceClientAreaOnly", wintypes.BOOL)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


dwmapi.DwmRegisterThumbnail.argtypes = [HWND, HWND, ctypes.POINTER(ctypes.c_ssize_t)]
dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.c_ssize_t]
dwmapi.DwmUpdateThumbnailProperties.argtypes = [ctypes.c_ssize_t, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)]
dwmapi.DwmQueryThumbnailSourceSize.argtypes = [ctypes.c_ssize_t, ctypes.POINTER(_SIZE)]
DWM_TNP_RECTDESTINATION, DWM_TNP_OPACITY, DWM_TNP_VISIBLE, DWM_TNP_SOURCECLIENTAREAONLY = 0x1, 0x4, 0x8, 0x10


class Thumbnails:
    """Live previews of other windows drawn by DWM inside our window."""

    def __init__(self):
        self._live: dict[int, int] = {}  # source hwnd -> thumbnail handle

    def show(self, dest: int, items: list[tuple[int, int, int, int, int]]):
        """items: (source hwnd, x, y, w, h) in physical pixels relative to dest's client area."""
        wanted = {hwnd for hwnd, *_ in items}
        for hwnd in list(self._live):
            if hwnd not in wanted:
                dwmapi.DwmUnregisterThumbnail(self._live.pop(hwnd))
        for hwnd, x, y, w, h in items:
            thumb = self._live.get(hwnd)
            if thumb is None:
                handle = ctypes.c_ssize_t()
                if dwmapi.DwmRegisterThumbnail(HWND(dest), HWND(hwnd), ctypes.byref(handle)) != 0:
                    continue
                thumb = self._live[hwnd] = handle.value
            size = _SIZE()
            dwmapi.DwmQueryThumbnailSourceSize(thumb, ctypes.byref(size))
            if size.cx <= 0 or size.cy <= 0:
                continue
            # Fit inside the box, keeping the window's shape, centred.
            ratio = min(w / size.cx, h / size.cy)
            tw, th = int(size.cx * ratio), int(size.cy * ratio)
            left, top = x + (w - tw) // 2, y + (h - th) // 2
            props = DWM_THUMBNAIL_PROPERTIES()
            props.dwFlags = DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_OPACITY | DWM_TNP_SOURCECLIENTAREAONLY
            props.rcDestination = wintypes.RECT(left, top, left + tw, top + th)
            props.opacity = 255
            props.fVisible = True
            props.fSourceClientAreaOnly = False
            dwmapi.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))

    def clear(self):
        for thumb in self._live.values():
            dwmapi.DwmUnregisterThumbnail(thumb)
        self._live.clear()
