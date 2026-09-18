"""Your desk on the Windows lock screen.

Windows will not let anyone draw on the lock screen. It is a separate secure
desktop, and that isolation is the thing that stops a program from imitating the
sign-in box - so no widget of ours can ever run there, however much we would
like one to.

What it will accept is a picture. So the desk is painted into one - the
wallpaper with your widgets on top, the same compositing `app.snapshot()` does
for a test render - and handed to Windows as the lock screen image.

This means the lock screen is a photograph of your desk rather than your desk:
whatever it shows was true when it was painted. Weather, the date, the song that
was playing and a battery level all survive that fine. A clock counting seconds
does not, which is why the interval is yours to choose and the option says so.

Setting the image goes through Windows.System.UserProfile.LockScreen, which
belongs to the signed-in user, so nothing here needs administrator rights and
nothing is changed for anybody else who uses the PC. The alternative - the
Personalization policy under HKLM - would force one picture on every account.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QImage, QPainter

# The PowerShell that hands one file to the lock screen. It is written next to
# the picture rather than passed with -Command so quoting cannot mangle a path,
# and it is regenerated on every run so an edited copy is never trusted.
_APPLY_PS1 = r"""
param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) { throw "no such picture: $Path" }
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
  $task.Wait(-1) | Out-Null
  $task.Result
}
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and -not $_.IsGenericMethod })[0]
function AwaitAction($action) {
  $task = $asTaskAction.Invoke($null, @($action))
  $task.Wait(-1) | Out-Null
}
[Windows.System.UserProfile.LockScreen, Windows.System.UserProfile, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
AwaitAction ([Windows.System.UserProfile.LockScreen]::SetImageFileAsync($file))
Write-Output 'ok'
"""


def _home() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk"


class LockScreen(QObject):
    """style/lock_screen: repaint the Windows lock screen from the desk."""

    def __init__(self, store, displays, wallpaper: Path):
        super().__init__()
        self._store, self._displays, self._wallpaper = store, displays, wallpaper
        self._enabled = False
        self._minutes = 0
        # Long by default: each pass grabs every widget and asks Windows to take
        # a new picture, which is not something to do every second.
        self._timer = QTimer(self, singleShot=False, timeout=self.refresh)
        store.changed.connect(self.configure)
        self.configure()

    # ---- on / off ----------------------------------------------------------------

    @Slot()
    def configure(self):
        section = self._store.config.get("lock_screen") or {}
        want = bool(section.get("enabled", False)) and not os.environ.get("UNIDESK_SNAPSHOT")
        minutes = max(1, int(section.get("every_minutes", 10) or 10))
        if want == self._enabled and minutes == self._minutes:
            return
        self._enabled, self._minutes = want, minutes
        self._timer.stop()
        if not want:
            return
        self._timer.setInterval(minutes * 60_000)
        self._timer.start()
        # Once now, so turning it on shows something without waiting a interval.
        QTimer.singleShot(1500, self.refresh)

    # ---- painting ----------------------------------------------------------------

    def _slot(self):
        """The screen the lock screen shows: the primary one."""
        slots = [s for s in self._displays.slots if s.desk_window is not None]
        if not slots:
            return None
        from PySide6.QtGui import QGuiApplication

        primary = QGuiApplication.primaryScreen()
        for slot in slots:
            if primary is not None and slot.screen is primary:
                return slot
        return slots[0]

    def _paint(self, out: Path) -> bool:
        """The wallpaper with the widgets on it, at this screen's size.

        The dock is deliberately left out: it is a thing you click, and a
        picture of one on the lock screen would only invite the attempt.
        """
        slot = self._slot()
        if slot is None:
            return False
        rect: QRect = slot.rect
        if rect.width() <= 0 or rect.height() <= 0:
            return False

        canvas = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(QColor("#101014"))
        painter = QPainter(canvas)
        wall = QImage(str(self._wallpaper))
        if not wall.isNull():
            scaled = wall.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            crop = QRect(
                (scaled.width() - rect.width()) // 2,
                (scaled.height() - rect.height()) // 2,
                rect.width(),
                rect.height(),
            )
            painter.drawImage(QPoint(0, 0), scaled, crop)
        widgets = slot.desk_window.grabWindow()
        if not widgets.isNull():
            painter.drawImage(slot.area.topLeft() - rect.topLeft(), widgets)
        painter.end()

        out.parent.mkdir(parents=True, exist_ok=True)
        # JPEG, because the lock screen is a photograph and a 4K PNG of one is
        # tens of megabytes that Windows only has to read back and re-encode.
        return bool(canvas.save(str(out), "JPG", 92))

    # ---- handing it to Windows ---------------------------------------------------

    def _apply(self, picture: Path) -> bool:
        script = _home() / "lockscreen.ps1"
        try:
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(_APPLY_PS1, encoding="utf-8")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), "-Path", str(picture)],
                capture_output=True,
                text=True,
                timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:  # a lock screen is never worth taking the app down
            print(f"[unidesk] lock screen: {e}")
            return False
        if result.returncode != 0 or "ok" not in (result.stdout or ""):
            print(f"[unidesk] lock screen refused: {(result.stderr or result.stdout or '').strip()[:200]}")
            return False
        return True

    @Slot()
    def refresh(self):
        """Paint the desk and give it to Windows. Safe to call at any time."""
        if not self._enabled:
            return
        # Two files, used alternately: Windows holds the one it was given open
        # for a while, and overwriting that same path is what makes it keep
        # showing the previous picture.
        picture = _home() / ("lockscreen-a.jpg" if self._flip() else "lockscreen-b.jpg")
        if self._paint(picture) and self._apply(picture):
            return
        print("[unidesk] lock screen was not updated")

    _use_a = False

    def _flip(self) -> bool:
        self._use_a = not self._use_a
        return self._use_a
