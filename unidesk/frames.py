"""Other apps' windows in the same colours (Windows 11): title bar, caption
text and border from the Material You palette, with the focused window's
border in the accent colour.

Only standard title bars change colour. Apps that draw their own (File
Explorer, Terminal, browsers) keep theirs and just get the border. The
minimize / maximize / close buttons stay Windows' own. Everything is put back
when unidesk quits or the option is turned off."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Slot

from . import desktop

user32 = desktop.user32
dwmapi = desktop.dwmapi
dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.UINT]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND

DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 20, 34, 35, 36
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF
MODES = ("themed", "border", "off")


def _colorref(hex_color: str) -> int:
    """#rrggbb -> COLORREF (0x00bbggrr)."""
    value = str(hex_color).lstrip("#")
    try:
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return DWMWA_COLOR_DEFAULT
    return r | g << 8 | b << 16


def _put(hwnd: int, attribute: int, value: int) -> bool:
    data = wintypes.DWORD(value & 0xFFFFFFFF)
    return dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)) == 0


def _dark_mode(hwnd: int) -> int:
    data = wintypes.DWORD()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(data), ctypes.sizeof(data)) == 0:
        return int(data.value)
    return 0


def reset_all_windows():
    """After unidesk was force-closed: every window's frame colours back to the
    system's. (Dark mode can't be told apart from an app's own, so it stays.)"""
    def visit(hwnd, _):
        if (user32.GetWindowLongPtrW(hwnd, desktop.GWL_STYLE) & desktop.WS_CAPTION) == desktop.WS_CAPTION:
            for attribute in (DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR, DWMWA_BORDER_COLOR):
                _put(hwnd, attribute, DWMWA_COLOR_DEFAULT)
        return True

    user32.EnumWindows(desktop.EnumWindowsProc(visit), 0)


class WindowFrames(QObject):
    """style.window_frames: themed (title bar + text + border) | border | off."""

    def __init__(self, store, theme):
        super().__init__()
        self._store, self._theme = store, theme
        self._own_pid = os.getpid()
        self._mode = "off"
        self._applied: dict[int, tuple] = {}   # hwnd -> the values last set
        self._dark_before: dict[int, int] = {}  # hwnd -> its own dark-mode setting, to put back
        self._events: desktop.WindowEvents | None = None
        self._sweep = QTimer(self, interval=3000, timeout=self.apply_all)   # windows opened in the background
        self._soon = QTimer(self, singleShot=True, interval=30, timeout=self.apply_all)
        store.changed.connect(self.configure)
        theme.colorsChanged.connect(self._soon.start)

    @Slot()
    def configure(self):
        mode = str((self._store.config.get("style") or {}).get("window_frames", "themed")).strip().lower()
        if mode in ("false", "no", "none", "0"):
            mode = "off"  # `window_frames: false` like the other switches
        mode = mode if mode in MODES else "themed"
        if os.environ.get("UNIDESK_SNAPSHOT"):
            mode = "off"  # test renders never touch real windows
        if mode == self._mode:
            return
        self.restore()
        self._mode = mode
        if mode == "off":
            self._sweep.stop()
            if self._events is not None:
                self._events.close()
                self._events = None
            return
        if self._events is None:
            self._events = desktop.WindowEvents(self._soon.start)  # focus moves: move the accent border
        self._sweep.start()
        self.apply_all()

    def _values(self, focused: bool) -> tuple:
        c = self._theme.c
        border = _colorref(c.get("primary" if focused else "outlineVariant", ""))
        if self._mode == "border":
            return None, None, None, border
        return (1 if self._theme.dark else 0, _colorref(c.get("primaryContainer", "")),
                _colorref(c.get("onPrimaryContainer", "")), border)

    def _eligible(self, hwnd: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return False
        if (user32.GetWindowLongPtrW(hwnd, desktop.GWL_STYLE) & desktop.WS_CAPTION) != desktop.WS_CAPTION:
            return False
        if user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE) & desktop.WS_EX_TOOLWINDOW:
            return False
        return desktop._pid(hwnd) != self._own_pid

    @Slot()
    def apply_all(self):
        if self._mode == "off":
            return
        focused = int(user32.GetForegroundWindow() or 0)
        seen: set[int] = set()

        def visit(hwnd, _):
            try:
                if self._eligible(hwnd):
                    seen.add(hwnd)
                    values = self._values(hwnd == focused)
                    if self._applied.get(hwnd) != values:
                        self._apply(hwnd, values)
            except Exception:
                pass
            return True

        user32.EnumWindows(desktop.EnumWindowsProc(visit), 0)
        for hwnd in [h for h in self._applied if h not in seen and not user32.IsWindow(h)]:
            self._applied.pop(hwnd, None)
            self._dark_before.pop(hwnd, None)

    def _apply(self, hwnd: int, values: tuple):
        dark, caption, text, border = values
        if dark is not None:
            if hwnd not in self._dark_before:
                self._dark_before[hwnd] = _dark_mode(hwnd)
            _put(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, dark)
        if caption is not None:
            _put(hwnd, DWMWA_CAPTION_COLOR, caption)
        if text is not None:
            _put(hwnd, DWMWA_TEXT_COLOR, text)
        _put(hwnd, DWMWA_BORDER_COLOR, border)
        self._applied[hwnd] = values

    @Slot()
    def restore(self):
        """Give every window its own frame back."""
        for hwnd, (dark, caption, text, _border) in self._applied.items():
            if not user32.IsWindow(hwnd):
                continue
            if caption is not None:
                _put(hwnd, DWMWA_CAPTION_COLOR, DWMWA_COLOR_DEFAULT)
            if text is not None:
                _put(hwnd, DWMWA_TEXT_COLOR, DWMWA_COLOR_DEFAULT)
            _put(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_DEFAULT)
            if hwnd in self._dark_before:
                _put(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, self._dark_before[hwnd])
        self._applied.clear()
        self._dark_before.clear()
