"""Show desktop, without losing the desk.

Windows' own Show desktop (Win+D, or the sliver at the end of the taskbar) is
not something unidesk can lean on. With the taskbar hidden the sliver is gone,
and Win+D decides for itself what counts as the desktop: the widgets survive it
only as long as their window is still owned by Progman, a link Qt quietly
breaks every time it re-shows a window.

So this does it the plain way. Every app window that has a place on the dock
is minimised, and nothing else is touched - the widgets and the dock are
unidesk's own windows, which the list never includes, so they are exactly
where they were and keep drawing. Pressing it again, while the desk is still
clear, brings back what it put away, in the order it was stacked.

It behaves like Windows' version in the ways that matter:
  * a window you had already minimised yourself stays minimised - it was
    never ours to bring back;
  * if you open something after clearing the desk, the next press clears
    that too rather than restoring the rest over the top of it - and the
    press after that brings everything back, the new window included.
"""
from __future__ import annotations

from typing import Callable


class ShowDesktop:
    """The toggle, with the window operations passed in so it can be tested
    without minimising anybody's real windows."""

    def __init__(
        self,
        windows: Callable[[], list[dict]],
        minimize: Callable[[int], None],
        restore: Callable[[int], None],
        is_minimized: Callable[[int], bool],
        exists: Callable[[int], bool],
        activate: Callable[[int], None],
    ):
        self._windows = windows
        self._minimize = minimize
        self._restore = restore
        self._is_minimized = is_minimized
        self._exists = exists
        self._activate = activate
        # What this put away, front-most first. Only these are ever restored.
        self._hidden: list[int] = []

    def _still_hidden(self) -> list[int]:
        """The windows this put away that are still gone. One closed, or
        brought back by hand, in the meantime is not ours to touch any more."""
        return [h for h in self._hidden if self._exists(h) and self._is_minimized(h)]

    def toggle(self) -> str:
        """Clear the desk, or bring it back. Answers which it did."""
        showing = [w["hwnd"] for w in self._windows() if not w.get("minimized")]
        waiting = self._still_hidden()

        if not showing and waiting:
            # The desk is clear and we have things put away: bring them back.
            # Back-most first, so that each one lands behind the next and the
            # window that was on top before ends up on top again.
            for hwnd in reversed(waiting):
                self._restore(hwnd)
            self._activate(waiting[0])
            self._hidden = []
            return "restored"

        if not showing:
            return "nothing"

        for hwnd in showing:
            self._minimize(hwnd)
        # Kept alongside whatever was already put away, so one press brings
        # all of it back rather than only what was opened since.
        self._hidden = showing + [h for h in waiting if h not in showing]
        return "cleared"
