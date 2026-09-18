"""Cookie-styled minimize / maximize / close buttons over the active window.

unidesk draws the buttons itself (Qt, like the widgets) in a small overlay laid
exactly over the window's real caption buttons, whose position Windows reports
through DWMWA_CAPTION_BUTTON_BOUNDS. Only the focused window is covered, so
there is no z-order fighting; apps that draw their own title bar (browsers,
VS Code, Terminal) are skipped.

The overlay is a QQuickView we position and show from here, so its lifetime and
geometry don't depend on the QML engine auto-showing a Window (which proved
unreliable). Nothing is injected into other processes; clicks are ordinary
WM_SYSCOMMAND messages."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRect, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQuick import QQuickView

from . import desktop

user32 = desktop.user32
dwmapi = desktop.dwmapi

DWMWA_CAPTION_BUTTON_BOUNDS = 5
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_CLOSE, SC_RESTORE = 0xF020, 0xF030, 0xF060, 0xF120
WS_MAXIMIZEBOX, WS_MINIMIZEBOX = 0x00010000, 0x00020000
EVENT_SYSTEM_MOVESIZESTART, EVENT_SYSTEM_MOVESIZEEND = 0x000A, 0x000B

user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsZoomed.argtypes = [wintypes.HWND]

SELF_DRAWN = {
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe", "vivaldi.exe",
    "code.exe", "code - insiders.exe", "cursor.exe", "discord.exe", "spotify.exe", "steam.exe",
    "steamwebhelper.exe", "windowsterminal.exe", "slack.exe", "obs64.exe", "telegram.exe", "whatsapp.exe", "zen.exe",
}
HERE = Path(__file__).resolve().parent


def _caption_button_bounds(hwnd: int):
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CAPTION_BUTTON_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        return None
    if r.right - r.left <= 0 or r.bottom - r.top <= 0:
        return None
    return r


class CaptionButtons(QObject):
    """Exposed to QML (inside the overlay view) as `Caption`."""

    changed = Signal()

    def __init__(self, store, theme):
        super().__init__()
        self._store, self._theme = store, theme
        self._own_pid = os.getpid()
        self._enabled = False
        self._target = 0
        self._rect = QRect()
        self._has_min = self._has_max = True
        self._maximized = False
        self._view: QQuickView | None = None
        self._events: desktop.WindowEvents | None = None
        self._move_hook = None
        self._poll = QTimer(self, interval=140, timeout=self._track)
        self._fast = QTimer(self, interval=16, timeout=self._track)
        store.changed.connect(self.configure)
        theme.colorsChanged.connect(self.changed)
        self.configure()

    # ---- on/off ----------------------------------------------------------------

    @Slot()
    def configure(self):
        style = self._store.config.get("style") or {}
        want = bool(style.get("window_buttons", False)) and not os.environ.get("UNIDESK_SNAPSHOT")
        if want == self._enabled:
            return
        self._enabled = want
        if want:
            self._ensure_view()
            self._events = desktop.WindowEvents(self._retarget)
            self._move_hook = _MoveSizeHook(self._on_movesize)
            self._poll.start()
            self._track()
        else:
            self._poll.stop()
            self._fast.stop()
            if self._events:
                self._events.close()
                self._events = None
            if self._move_hook:
                self._move_hook.close()
                self._move_hook = None
            if self._view:
                self._view.hide()

    def _ensure_view(self):
        if self._view is not None:
            return
        view = QQuickView()
        view.setColor(QColor(0, 0, 0, 0))
        view.setFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                      | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        ctx = view.rootContext()
        ctx.setContextProperty("Caption", self)
        ctx.setContextProperty("Theme", self._theme)
        view.setSource(QUrl.fromLocalFile(str(HERE / "qml" / "CaptionOverlay.qml")))
        if view.status() == QQuickView.Status.Error:
            for e in view.errors():
                print(f"[unidesk] caption overlay QML error: {e.toString()}")
        self._view = view

    def _on_movesize(self, dragging: bool):
        if dragging and self._enabled:
            self._fast.start()
        else:
            self._fast.stop()

    def _retarget(self):
        if self._enabled:
            self._track()

    # ---- tracking --------------------------------------------------------------

    def _eligible(self, hwnd: int) -> bool:
        if not hwnd or desktop._pid(hwnd) == self._own_pid:
            return False
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return False
        if (user32.GetWindowLongPtrW(hwnd, desktop.GWL_STYLE) & desktop.WS_CAPTION) != desktop.WS_CAPTION:
            return False
        if user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE) & desktop.WS_EX_TOOLWINDOW:
            return False
        try:
            if desktop.process_name(desktop._pid(hwnd)).lower() in SELF_DRAWN:
                return False
        except Exception:
            pass
        return True

    @Slot()
    def _track(self):
        fg = int(user32.GetForegroundWindow() or 0)
        bounds = _caption_button_bounds(fg) if self._eligible(fg) else None
        if bounds is None:
            if self._view and self._view.isVisible():
                self._view.hide()
            self._target = 0
            return

        win = wintypes.RECT()
        user32.GetWindowRect(fg, ctypes.byref(win))
        dpr = self._dpr(win.left + bounds.left, win.top + bounds.top)
        rect = QRect(round((win.left + bounds.left) / dpr), round((win.top + bounds.top) / dpr),
                     round((bounds.right - bounds.left) / dpr), round((bounds.bottom - bounds.top) / dpr))
        style = user32.GetWindowLongPtrW(fg, desktop.GWL_STYLE)
        has_min, has_max = bool(style & WS_MINIMIZEBOX), bool(style & WS_MAXIMIZEBOX)
        maximized = bool(user32.IsZoomed(fg))

        state_changed = (has_min, has_max, maximized) != (self._has_min, self._has_max, self._maximized) or fg != self._target
        self._target, self._has_min, self._has_max, self._maximized = fg, has_min, has_max, maximized
        if state_changed:
            self.changed.emit()

        self._ensure_view()
        v = self._view
        if rect != self._rect or not v.isVisible():
            self._rect = rect
            v.setGeometry(rect)
            if not v.isVisible():
                v.show()
                desktop.set_activatable(int(v.winId()), False)
            desktop.bring_to_front(int(v.winId()))

    @staticmethod
    def _dpr(x: int, y: int) -> float:
        from PySide6.QtCore import QPoint

        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        return screen.devicePixelRatio() if screen else 1.0

    # ---- QML -------------------------------------------------------------------

    @Property(int, notify=changed)
    def count(self):
        return 1 + self._has_min + self._has_max

    @Property(bool, notify=changed)
    def hasMin(self):
        return self._has_min

    @Property(bool, notify=changed)
    def hasMax(self):
        return self._has_max

    @Property(bool, notify=changed)
    def maximized(self):
        return self._maximized

    @Slot(str)
    def command(self, which: str):
        if not self._target:
            return
        code = {"min": SC_MINIMIZE, "close": SC_CLOSE,
                "max": SC_RESTORE if self._maximized else SC_MAXIMIZE}.get(which)
        if code is not None:
            user32.SendMessageW(self._target, WM_SYSCOMMAND, code, 0)
            QTimer.singleShot(30, self._track)


class _MoveSizeHook:
    """Tells us when the user starts / stops dragging or resizing any window."""

    def __init__(self, callback):
        self._cb = callback
        self._proc = desktop.WinEventProc(self._on)
        self._hooks = []
        for evt in (EVENT_SYSTEM_MOVESIZESTART, EVENT_SYSTEM_MOVESIZEEND):
            h = user32.SetWinEventHook(evt, evt, None, self._proc, 0, 0, desktop.WINEVENT_SKIPOWNPROCESS)
            if h:
                self._hooks.append(h)

    def _on(self, hook, event, *_):
        self._cb(event == EVENT_SYSTEM_MOVESIZESTART)

    def close(self):
        for h in self._hooks:
            user32.UnhookWinEvent(h)
        self._hooks.clear()
