"""Win32 glue: keep desk windows on the desktop layer, and notice which
monitors a fullscreen app (a game, a video) covers so unidesk can go idle there."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

GWL_STYLE, GWL_EXSTYLE = -16, -20
GWLP_HWNDPARENT = -8
GW_OWNER = 4
WS_CAPTION = 0x00C00000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND = 0x0016, 0x0017
WINEVENT_SKIPOWNPROCESS = 0x0002

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
WinEventProc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

for name, res, args in [
    ("FindWindowW", wintypes.HWND, [wintypes.LPCWSTR, wintypes.LPCWSTR]),
    ("GetWindowLongPtrW", ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int]),
    ("SetWindowLongPtrW", ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]),
    ("SetWindowPos", wintypes.BOOL, [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]),
    ("GetWindow", wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
    ("GetWindowRect", wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
    ("GetClassNameW", ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
    ("GetWindowThreadProcessId", wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
    ("IsWindowVisible", wintypes.BOOL, [wintypes.HWND]),
    ("IsIconic", wintypes.BOOL, [wintypes.HWND]),
    ("IsZoomed", wintypes.BOOL, [wintypes.HWND]),
    ("EnumWindows", wintypes.BOOL, [EnumWindowsProc, wintypes.LPARAM]),
    ("EnumDisplayMonitors", wintypes.BOOL, [wintypes.HDC, ctypes.c_void_p, MonitorEnumProc, wintypes.LPARAM]),
    ("MonitorFromWindow", wintypes.HMONITOR, [wintypes.HWND, wintypes.DWORD]),
    ("GetMonitorInfoW", wintypes.BOOL, [wintypes.HMONITOR, ctypes.c_void_p]),
    ("SetWinEventHook", wintypes.HANDLE, [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, WinEventProc, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]),
    ("UnhookWinEvent", wintypes.BOOL, [wintypes.HANDLE]),
]:
    fn = getattr(user32, name)
    fn.restype, fn.argtypes = res, args

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.UINT]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE


# ---- the desktop layer ------------------------------------------------------------

def _owner(hwnd: int) -> int:
    return int(user32.GetWindow(wintypes.HWND(hwnd), GW_OWNER) or 0)


def pin_to_desktop(hwnd: int):
    """Owned by the desktop, so it sits just above the wallpaper and comes along
    when the desktop is brought forward (Show desktop); and no Alt+Tab entry.
    Qt clears the owner every time it shows a window, so call this on every show."""
    h = wintypes.HWND(hwnd)
    ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
    if not ex & WS_EX_TOOLWINDOW:
        user32.SetWindowLongPtrW(h, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW)
    progman = user32.FindWindowW("Progman", None)
    if progman and _owner(hwnd) != int(progman):
        user32.SetWindowLongPtrW(h, GWLP_HWNDPARENT, progman)


def pinned(hwnd: int) -> bool:
    """False once the owner link is gone (Qt re-showed the window, or Explorer restarted)."""
    progman = user32.FindWindowW("Progman", None)
    return not progman or _owner(hwnd) == int(progman)


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


# ---- monitors -----------------------------------------------------------------------

def monitors() -> dict[str, tuple[int, int, int, int]]:
    """Device name (what QScreen.name() reports, e.g. \\\\.\\DISPLAY1) -> rect in physical pixels."""
    out: dict[str, tuple[int, int, int, int]] = {}

    def visit(hmon, _hdc, _rect, _data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            out[info.szDevice] = (r.left, r.top, r.right, r.bottom)
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(visit), 0)
    return out


def window_monitor(hwnd: int) -> str:
    """Device name of the monitor a window is (mostly) on."""
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    hmon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    return info.szDevice if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(info)) else ""


# ---- fullscreen apps --------------------------------------------------------------------
# Never "a fullscreen app": the desktop, taskbars, and the shell's own flyouts,
# switchers and overlays (Start, search, Alt+Tab, Task View, widgets, the
# screenshot overlay, Game Bar...), even though several of them cover a monitor.

_DESKTOP_CLASSES = {"Progman", "WorkerW"}
_SHELL_CLASSES = {
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow",
    "ForegroundStaging", "MultitaskingViewFrame", "TaskSwitcherWnd", "TaskSwitcherOverlayWnd",
    "ApplicationManager_ImmersiveShellWindow", "ImmersiveLauncher", "EdgeUiInputTopWndClass", "EdgeUiInputWndClass",
    "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland", "Shell_InputSwitchTopLevelWindow",
    "SnapAssistFlyout", "RainmeterMeterWindow",
}
_SHELL_PROCESSES = {
    "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe", "searchapp.exe",
    "textinputhost.exe", "lockapp.exe", "shellhost.exe", "widgets.exe", "widgetboard.exe", "microsoftstartfeedprovider.exe",
    "screenclippinghost.exe", "snippingtool.exe", "gamebar.exe", "xboxgamebarwidgets.exe", "magnify.exe", "rainmeter.exe",
}


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


def process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def fullscreen_monitors(own_pid: int) -> set[str]:
    """Device names of the monitors where a fullscreen app is in front.

    Windows are visited front to back, and on each monitor the first real app
    window decides: covering the whole monitor means fullscreen, any other
    ordinary window in front means not. Tool windows, click-through overlays
    (Rainmeter skins, game overlays), popups owned by another window, windows
    on other virtual desktops, the shell's flyouts and small always-on-top
    windows (picture-in-picture) don't decide; reaching the desktop itself
    (Show desktop) settles every monitor left as not fullscreen."""
    undecided = monitors()
    busy: set[str] = set()
    names: dict[int, str] = {}

    def visit(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            cls = _class(hwnd)
            if cls in _DESKTOP_CLASSES:
                undecided.clear()
                return False
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            if ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) or (ex & WS_EX_LAYERED and ex & WS_EX_TRANSPARENT):
                return True
            if cls in _SHELL_CLASSES or user32.GetWindow(hwnd, GW_OWNER) or _cloaked(hwnd):
                return True
            pid = _pid(hwnd)
            if pid == own_pid:
                return True
            if pid not in names:
                names[pid] = process_name(pid)
            if names[pid] in _SHELL_PROCESSES:
                return True
            r = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
                return True
            # A maximised window with a title bar spills a few pixels past the
            # screen edges; that is not fullscreen, even with the taskbar hidden.
            framed = (user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & WS_CAPTION) == WS_CAPTION
            if not (framed and user32.IsZoomed(hwnd)):
                for device, (left, top, right, bottom) in list(undecided.items()):
                    if r.left <= left and r.top <= top and r.right >= right and r.bottom >= bottom:
                        busy.add(device)
                        del undecided[device]
            if not ex & WS_EX_TOPMOST:
                undecided.pop(window_monitor(hwnd), None)
            return bool(undecided)
        except Exception:
            return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return busy


class WindowEvents:
    """Calls `callback()` when the foreground window changes or a window is
    minimised or restored (delivered on the Qt thread)."""

    def __init__(self, callback):
        self._proc = WinEventProc(lambda *_: callback())
        self._hooks = []
        for low, high in ((EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND), (EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND)):
            hook = user32.SetWinEventHook(low, high, None, self._proc, 0, 0, WINEVENT_SKIPOWNPROCESS)
            if hook:
                self._hooks.append(hook)

    def close(self):
        for hook in self._hooks:
            user32.UnhookWinEvent(hook)
        self._hooks.clear()
