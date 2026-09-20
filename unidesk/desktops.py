"""Which virtual desktop is showing, so a widget can be kept to one of them.

Windows documents almost nothing about virtual desktops. The public interface
(IVirtualDesktopManager) can say which desktop an ordinary window is on, and
that is it - there is no "which one am I looking at". You can get close by
asking the windows that are open, but that fails on exactly the desktop this
feature is for: a second desktop kept clear for widgets has no windows on it
to ask, and every window unidesk owns answers "yes, I'm on this one" wherever
you are, because a window with no desktop of its own is treated as being on
all of them.

So this leans on pyvda, which wraps the interfaces Explorer uses internally.
Those are undocumented and change between Windows builds, which is why it is
optional: without it, or on a build it does not understand, widgets simply
show on every desktop, which is what they did before any of this.

The polling is done off the main thread. It is a fast call, but it is a call
into the shell, and the desk repainting is not something to make wait on it.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Property, QObject, Signal, Slot

# How often to look. A desktop switch is animated and takes longer than this,
# so widgets change over while the animation is still running.
POLL_SECONDS = 0.3


def _read():
    """(number of the desktop showing, how many there are), or (0, 0)."""
    import pyvda

    return pyvda.VirtualDesktop.current().number, len(pyvda.get_virtual_desktops())


class Desktops(QObject):
    """Exposed to QML as `Desktops`: `.current`, `.count`, `.available`."""

    changed = Signal()
    _seen = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._current = 0
        self._count = 0
        self._available = False
        self._checked = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen.connect(self._on_seen)

    # ---- lifecycle --------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if not self._usable():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread = None

    def _usable(self) -> bool:
        """Whether this machine's Windows is one pyvda understands. Asked once:
        a build it cannot read will not start working later."""
        if self._checked:
            return self._available
        self._checked = True
        try:
            from .dock import winapi

            winapi.com_init()
            current, count = _read()
            self._available = current > 0 and count > 0
            if self._available:
                self._current, self._count = current, count
        except Exception as e:
            print(f"[unidesk] virtual desktops unavailable: {e}")
            self._available = False
        return self._available

    def _watch(self):
        from .dock import winapi

        winapi.com_init()
        failures = 0
        while not self._stop.wait(POLL_SECONDS):
            try:
                current, count = _read()
                failures = 0
            except Exception as e:
                failures += 1
                # Explorer restarting takes the interfaces with it for a
                # moment. Give up only if it stays broken.
                if failures == 10:
                    print(f"[unidesk] virtual desktops stopped answering: {e}")
                    return
                continue
            if (current, count) != (self._current, self._count):
                self._seen.emit(current, count)

    @Slot(int, int)
    def _on_seen(self, current: int, count: int):
        if (current, count) == (self._current, self._count):
            return
        self._current, self._count = current, count
        self.changed.emit()

    # ---- what QML binds to ------------------------------------------------

    @Property(int, notify=changed)
    def current(self) -> int:
        """The desktop showing, counting from 1. 0 when it cannot be told -
        in which case a widget kept to a desktop is shown rather than hidden,
        because a widget nobody can find is worse than one in the wrong place."""
        return self._current

    @Property(int, notify=changed)
    def count(self) -> int:
        return self._count

    @Property(bool, notify=changed)
    def available(self) -> bool:
        return self._available
