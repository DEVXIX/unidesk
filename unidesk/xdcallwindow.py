"""The window a call arrives in: bottom right, above everything, sliding up.

It is its own window rather than part of the xD widget on purpose. A call has
to reach you when you are playing something full screen, or reading a page with
the desk behind it - a card drawn inside a widget can only be seen by somebody
already looking at that widget, which is nobody, which is the same as no ring
at all.

It borrows the caption overlay's flags (see captionbuttons.py): frameless, a
Tool so it keeps out of the taskbar and the alt-tab list, always on top, and
explicitly not taking focus. That last one matters most: a ring that pulls
focus out of a full-screen game to show itself is worse than a missed call.
Clicks still arrive - not taking focus is not the same as not being clickable.

The window stands still and the card inside it slides. Moving a window every
frame is how an animation on Windows comes out as a stutter; moving a rectangle
inside a window that is already there does not.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Qt, Slot
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQuick import QQuickView

HERE = Path(__file__).parent

# Room for the card, the shadow, and the distance it travels on its way up.
WIDTH = 330
HEIGHT = 190
# How far from the corner it sits. Clear of the dock, which lives along the
# bottom edge.
MARGIN_RIGHT = 18
MARGIN_BOTTOM = 96


class XDCallWindow(QObject):
    """Shows the call card whenever there is a call, and hides it when there is not."""

    def __init__(self, calls, theme, store):
        super().__init__()
        self._calls, self._theme, self._store = calls, theme, store
        self._view: QQuickView | None = None
        calls.changed.connect(self._sync)
        self._sync()

    # ---- the window --------------------------------------------------------------

    def _flags(self, on_top: bool = True):
        """Frameless, out of the taskbar, and above everything while it rings.

        It only ever exists while a call is ringing, and a ring has to be
        visible over whatever is full screen - so on top is not conditional.
        """
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        return flags | Qt.WindowStaysOnTopHint if on_top else flags

    def _ensure(self):
        if self._view is not None:
            return
        view = QQuickView()
        view.setColor(QColor(0, 0, 0, 0))
        # No WindowDoesNotAcceptFocus even though the caption overlay uses it:
        # answering a call is a click, and a window that refuses focus outright
        # can stop receiving them.
        view.setFlags(self._flags(True))
        view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        # Sized before the source is set, not after. SizeRootObjectToView hands
        # the root item the view's size, and a root item told it is 0x0 while it
        # is being built lays everything out against nothing.
        view.resize(WIDTH, HEIGHT)
        ctx = view.rootContext()
        ctx.setContextProperty("Calls", self._calls)
        ctx.setContextProperty("Theme", self._theme)
        ctx.setContextProperty("CallWindow", self)
        view.setSource(QUrl.fromLocalFile(str(HERE / "qml" / "CallCard.qml")))
        if view.status() == QQuickView.Status.Error:
            for error in view.errors():
                print(f"[unidesk] call card QML error: {error.toString()}")
        self._view = view

    def _place(self):
        view = self._view
        if view is None:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        view.setPosition(
            area.right() - WIDTH - MARGIN_RIGHT + 1,
            area.bottom() - HEIGHT - MARGIN_BOTTOM + 1,
        )

    @Slot()
    def _sync(self):
        # Ringing only. Once a call is answered it belongs in the xD widget,
        # which has room for the avatar, the volume, the devices and the rest;
        # a corner popup is the wrong shape for anything but "answer or not".
        wanted = bool(self._calls.isRinging or self._calls.isOutgoing)
        if not wanted:
            if self._view is not None:
                self._view.hide()
            return
        self._ensure()
        view = self._view
        if view is None:
            return

        self._place()
        if not view.isVisible():
            view.show()

    @Slot()
    def dismiss(self):
        """Put the card away without touching the call - the dock and the widget
        still have it, and it comes back if anything changes."""
        if self._view is not None:
            self._view.hide()
