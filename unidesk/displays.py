"""Monitors: every screen gets its own desk window (and dock). Screens are
numbered for config.yaml: 1 is the main display, then the others from left
to right; a widget's `screen` says which one it lives on."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QPoint, QRect, QSize, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtQml import QQmlComponent

HERE = Path(__file__).resolve().parent
SNAPSHOT = os.environ.get("UNIDESK_SNAPSHOT", "")
# Snapshots only: pretend the main display is this big, e.g. 3440x1440.
SNAPSHOT_SIZE = os.environ.get("UNIDESK_SNAPSHOT_SIZE", "")


class ScreenSlot(QObject):
    """One monitor as its desk and dock windows see it (`slot` in QML)."""

    changed = Signal()
    suspendedChanged = Signal()

    def __init__(self, screen):
        super().__init__()
        self.screen = screen
        self.desk_window = None
        self.dock_window = None
        self._number = 1
        self._suspended = False
        screen.geometryChanged.connect(lambda _: self.changed.emit())
        screen.availableGeometryChanged.connect(lambda _: self.changed.emit())

    def set_number(self, number: int):
        if number != self._number:
            self._number = number
            self.changed.emit()

    def set_suspended(self, on: bool):
        if on != self._suspended:
            self._suspended = on
            self.suspendedChanged.emit()

    def _snapshot(self, rect: QRect, full: bool) -> QRect:
        rect = QRect(rect)
        if SNAPSHOT:
            if SNAPSHOT_SIZE:
                w, _, h = SNAPSHOT_SIZE.partition("x")
                real = QGuiApplication.primaryScreen().geometry()
                if self.primary:
                    inset = self.screen.geometry().height() - self.screen.availableGeometry().height()
                    rect.setSize(QSize(int(w), int(h) - (0 if full else inset)))
                elif rect.x() >= real.right():
                    rect.translate(int(w) - real.width(), 0)  # make room for the bigger main display
            rect.translate(-20000, 0)  # render far off-screen; see app.snapshot()
        return rect

    @Property(int, notify=changed)
    def number(self):
        return self._number

    @Property(str, notify=changed)
    def name(self):
        return self.screen.name()

    @Property(bool, notify=changed)
    def primary(self):
        return self.screen == QGuiApplication.primaryScreen()

    @Property(QRect, notify=changed)
    def area(self):
        """The usable part (above the dock and taskbar), where widgets go."""
        return self._snapshot(self.screen.availableGeometry(), False)

    @Property(QRect, notify=changed)
    def rect(self):
        return self._snapshot(self.screen.geometry(), True)

    @Property(bool, notify=suspendedChanged)
    def suspended(self):
        return self._suspended


class Displays(QObject):
    """Keeps a numbered ScreenSlot per monitor, with a desk window on each and a
    dock wherever `want_dock(slot)` says so."""

    screensChanged = Signal()

    def __init__(self, app):
        super().__init__()
        self._app = app
        self.slots: list[ScreenSlot] = []
        self._engine = None
        self._desk_component = None
        self._dock_component = None
        self.want_dock = lambda slot: False
        self.before_close = lambda window: None  # lets the dock give back its reserved space
        self._rescan_soon = QTimer(self, singleShot=True, interval=0, timeout=self._rescan)
        app.screenAdded.connect(lambda _: self._rescan_soon.start())
        app.screenRemoved.connect(self._screen_removed)
        app.primaryScreenChanged.connect(lambda _: self._rescan_soon.start())
        self._rescan()

    # ---- screens ---------------------------------------------------------------

    def _screen_removed(self, screen):
        # Close its windows now, while the screen still exists.
        for slot in [s for s in self.slots if s.screen == screen]:
            self._close(slot)
            self.slots.remove(slot)
        self._rescan_soon.start()

    def _rescan(self):
        screens = list(self._app.screens())
        for slot in [s for s in self.slots if s.screen not in screens]:
            self._close(slot)
            self.slots.remove(slot)
        for screen in screens:
            if not any(s.screen == screen for s in self.slots):
                slot = ScreenSlot(screen)
                screen.geometryChanged.connect(lambda _: self._rescan_soon.start())
                self.slots.append(slot)
        primary = self._app.primaryScreen()
        self.slots.sort(key=lambda s: (s.screen != primary, s.screen.geometry().x(), s.screen.geometry().y()))
        for number, slot in enumerate(self.slots, 1):
            slot.set_number(number)
        self.sync_windows()
        self.screensChanged.emit()

    def slot_number(self, wanted: int) -> int:
        """The screen a widget really shows on: its own, or the main display while that one is unplugged."""
        return wanted if 1 <= wanted <= len(self.slots) else 1

    def slot_at(self, x: float, y: float) -> ScreenSlot | None:
        screen = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        return next((s for s in self.slots if s.screen == screen), None)

    def slot_at_cursor(self) -> ScreenSlot | None:
        pos = QCursor.pos()
        return self.slot_at(pos.x(), pos.y())

    def set_suspended(self, devices: set[str]):
        for slot in self.slots:
            slot.set_suspended(slot.screen.name() in devices)

    def desk_windows(self) -> list:
        return [s.desk_window for s in self.slots if s.desk_window is not None]

    def dock_windows(self) -> list:
        return [s.dock_window for s in self.slots if s.dock_window is not None]

    # ---- windows ---------------------------------------------------------------

    def attach(self, engine) -> bool:
        """Start making windows (after the QML context is set up). False if the QML is broken."""
        self._engine = engine
        self._desk_component = QQmlComponent(engine, QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
        self._dock_component = QQmlComponent(engine, QUrl.fromLocalFile(str(HERE / "qml" / "DockBar.qml")))
        for component in (self._desk_component, self._dock_component):
            if component.isError():
                for error in component.errors():
                    print(f"[unidesk] {error.toString()}")
                return False
        self.sync_windows()
        return True

    def _create(self, component, slot):
        window = component.createWithInitialProperties({"slot": slot}, self._engine.rootContext())
        if window is None:
            for error in component.errors():
                print(f"[unidesk] {error.toString()}")
        return window

    def sync_windows(self):
        if self._engine is None:
            return
        for slot in self.slots:
            if slot.desk_window is None:
                slot.desk_window = self._create(self._desk_component, slot)
            wanted = bool(self.want_dock(slot))
            if wanted and slot.dock_window is None:
                slot.dock_window = self._create(self._dock_component, slot)
            elif not wanted and slot.dock_window is not None:
                self._close_window(slot.dock_window)
                slot.dock_window = None

    def _close(self, slot: ScreenSlot):
        for window in (slot.desk_window, slot.dock_window):
            if window is not None:
                self._close_window(window)
        slot.desk_window = slot.dock_window = None

    def _close_window(self, window):
        self.before_close(window)
        window.setProperty("ready", False)
        window.close()
        window.deleteLater()
