"""The sign-in screen's accent, kept the same colour as the desk.

The "Sign in" button, the focus rings and the spinner on the Windows sign-in
screen are all drawn in the accent colour - and not yours. The sign-in screen
runs before anybody has signed in, so it reads its colour out of the .DEFAULT
hive, which is a profile nobody uses and which still holds whatever Windows
shipped with (#0078D7, the stock blue). Changing your own accent in Settings
never touches it, which is why the button stays that blue however the desk
looks.

So this writes the desk's own accent there instead. The colour is whatever the
theme is using at the time, which means it follows the wallpaper the way every
other accent on the desk does.

What it cannot do is change the button's SHAPE. LogonUI draws it, it is not a
themable surface, and nothing short of patching system binaries would round its
corners - which is not a trade worth making for one button.

Those keys belong to the SYSTEM profile, so unidesk cannot write them until
tools/allow-signin-accent.ps1 has been run once as administrator; it grants
this account write on those two keys and nothing else. Until then everything
here runs and says what it would have written.

The stored form is a DWORD in ABGR order - 0xAABBGGRR, not the RGB you would
write in CSS - which is worth saying out loud because a red accent written the
obvious way comes out blue and looks like it worked.
"""
from __future__ import annotations

import os
import winreg
from typing import Iterator

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QColor

# HKEY_USERS\.DEFAULT - the profile the sign-in screen runs as.
ACCENT_KEY = r".DEFAULT\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
DWM_KEY = r".DEFAULT\Software\Microsoft\Windows\DWM"


def abgr(color: QColor) -> int:
    """A colour as Windows stores it: 0xAABBGGRR."""
    return (0xFF << 24) | (color.blue() << 16) | (color.green() << 8) | color.red()


def _darker(color: QColor, amount: int = 118) -> QColor:
    """The shade Windows uses for Start, a step down from the accent."""
    return color.darker(amount)


class SignInAccent(QObject):
    """lock_screen.sign_in_accent: paint the sign-in button in the desk's colour."""

    def __init__(self, store, theme):
        super().__init__()
        self._store, self._theme = store, theme
        self._enabled = False
        self._last = ""
        # Said once per colour rather than on every repaint: without the grant
        # this is the state of things for good, and a line about it in the log
        # every time the wallpaper shifts is just noise.
        self._warned = ""
        # Tried again now and then, because the thing most likely to be
        # standing in the way - the one-off grant in
        # tools/allow-signin-accent.ps1 - is usually given while unidesk is
        # already running, and nothing about giving it tells the desk. Without
        # this the colour waits for the next wallpaper change or restart.
        self._retry = QTimer(self, singleShot=False, interval=180_000, timeout=self.apply)
        store.changed.connect(self.configure)
        theme.colorsChanged.connect(self.apply)
        self.configure()

    def _section(self) -> dict:
        return (self._store.config.get("lock_screen") or {}).get("sign_in_accent") or {}

    @Slot()
    def configure(self):
        want = bool(self._section().get("enabled", False)) and not os.environ.get("UNIDESK_SNAPSHOT")
        if want == self._enabled:
            return
        self._enabled = want
        self._retry.stop()
        if want:
            self._retry.start()
            QTimer.singleShot(8_000, self.apply)

    def _color(self) -> QColor:
        """What the widgets are accented with right now."""
        chosen = str(self._section().get("color") or "").strip()
        if chosen:
            color = QColor(chosen)
            if color.isValid():
                return color
        raw = str((self._theme.c or {}).get("primary") or "")
        color = QColor(raw)
        return color if color.isValid() else QColor("#8ab4f8")

    def _writes(self, color: QColor) -> Iterator[tuple[str, str, int]]:
        """Every value that has to move together, as (key, name, dword).

        AccentColorMenu is the button; DWM's AccentColor is what the shell reads
        for the same colour; StartColorMenu is the step-down shade beside it. A
        subset of these written alone leaves the sign-in screen half repainted.
        """
        main, down = abgr(color), abgr(_darker(color))
        yield ACCENT_KEY, "AccentColorMenu", main
        yield ACCENT_KEY, "StartColorMenu", down
        yield DWM_KEY, "AccentColor", main
        # The DWM colourisation carries its own alpha, which Windows keeps at
        # 0xC4; changing it makes the glass behind the sign-in box the wrong
        # weight, so only the colour part is replaced.
        yield DWM_KEY, "ColorizationColor", (0xC4 << 24) | (main & 0x00FFFFFF)

    def read(self) -> dict[str, int]:
        """What is there now, for saying what changed."""
        out: dict[str, int] = {}
        for key, name, _ in self._writes(QColor("#000000")):
            try:
                with winreg.OpenKey(winreg.HKEY_USERS, key) as handle:
                    out[f"{key}\\{name}"] = winreg.QueryValueEx(handle, name)[0]
            except OSError:
                continue
        return out

    @Slot()
    def apply(self):
        """Put the desk's accent where the sign-in screen will read it."""
        if not self._enabled:
            return
        color = self._color()
        if color.name() == self._last:
            return

        wrote = denied = 0
        for key, name, value in self._writes(color):
            try:
                with winreg.OpenKey(winreg.HKEY_USERS, key, 0, winreg.KEY_SET_VALUE) as handle:
                    winreg.SetValueEx(handle, name, 0, winreg.REG_DWORD, value)
                wrote += 1
            except PermissionError:
                denied += 1
            except OSError as e:
                print(f"[unidesk] sign-in accent: {name}: {e}")

        if denied:
            if self._warned == color.name():
                return
            self._warned = color.name()
            print(
                f"[unidesk] sign-in accent would be {color.name()}, but the sign-in screen's "
                "own settings are not writable yet - run tools\\allow-signin-accent.ps1 "
                "once as administrator"
            )
            return
        self._last = color.name()
        print(f"[unidesk] sign-in accent: {color.name()} ({wrote} values)")
