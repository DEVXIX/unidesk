"""Your sign-in picture: an avatar in one of the desk's own shapes.

This is the round picture above your name on the Windows sign-in screen, which
is a different thing from the wallpaper lockscreen.py paints - that is what you
see before you press a key, this is what you see after.

Windows crops an account picture to a circle, so the shape is drawn inside that
circle rather than out to its edges: a star whose points reach the corners of
its own box is a star with its points cropped off. What surrounds it is your
wallpaper, blurred, so the picture sits on the desktop it belongs to instead of
on a disc of flat colour.

The shape is picked at random every time this runs, so signing in is not quite
the same picture twice.

Where it goes: the exact files the registry already points at, under
C:\\Users\\Public\\AccountPictures\\<SID>\\. Those belong to SYSTEM and the
Administrators group, so unidesk cannot write them until somebody runs
tools\\allow-signin-picture.ps1 once as administrator - it grants this one
account Modify on its own picture folder and nothing else. Without that the
pictures are still drawn, into unidesk's own folder, ready to be picked by hand
in Settings > Accounts > Your info.

The one thing that cannot be done from here is the font your name is drawn in.
That label belongs to LogonUI, and the only lever Windows offers is substituting
the system UI font everywhere - not worth it for one piece of text.
"""
from __future__ import annotations

import math
import os
import random
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from .providers.net import get_bytes

# Every size Windows asks for. The registry names them one by one, and a size
# it cannot find it makes by blurring another, so all of them are written.
SIZES = (32, 40, 48, 64, 96, 192, 208, 240, 424, 448, 1080)

# The same shapes as qml/Shapes.js: r(t) = 1 - amp + amp * cos(lobes * t).
# Kept as numbers here rather than read from that file, because one is drawn by
# QML and this is drawn by QPainter - but they are meant to look like each
# other, so a change to one belongs in both.
SPECS = {
    "cookie": (9, 0.07, 0.0),
    "cookie12": (12, 0.05, 0.0),
    "flower": (8, 0.065, 0.0),
    "star": (8, 0.12, 0.0),
    "burst": (12, 0.09, 0.0),
    "clover": (4, 0.16, 0.0),
    "pentagon": (5, 0.06, math.pi),
    "circle": (0, 0.0, 0.0),
}

# How much of the circle the shape fills. Right up to it: the picture should be
# as big as the space Windows gives it. What makes the shape read is the
# wallpaper showing through where the shape dips inwards, not a gap around it.
INSET = 0.98


def _home() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk"


def shape_names() -> list[str]:
    """The shapes worth using here.

    squircle and pill are deliberately not among them: they are box shapes, and
    Windows crops an account picture to a circle, so both arrive with their
    corners sliced off. shape_path still draws them for anyone who names one.
    """
    return list(SPECS.keys())


def shape_path(name: str, size: float) -> QPainterPath:
    """One expressive shape as a closed path filling a box of `size`."""
    path = QPainterPath()
    half = size / 2
    if name in ("squircle", "pill"):
        power = 4.5 if name == "squircle" else 12.0
        for i in range(200):
            t = i / 200 * math.tau
            c, s = math.cos(t), math.sin(t)
            x = half + half * math.copysign(abs(c) ** (2 / power), c)
            y = half + half * math.copysign(abs(s) ** (2 / power), s)
            path.lineTo(QPointF(x, y)) if i else path.moveTo(QPointF(x, y))
        path.closeSubpath()
        return path

    lobes, amp, rot = SPECS.get(name, SPECS["cookie"])
    for i in range(240):
        t = i / 240 * math.tau
        r = 1 - amp + amp * math.cos(lobes * (t + rot / max(lobes, 1)))
        x = half + r * half * math.sin(t)
        y = half - r * half * math.cos(t)
        path.lineTo(QPointF(x, y)) if i else path.moveTo(QPointF(x, y))
    path.closeSubpath()
    return path


def _blurred(image: QImage, size: int) -> QImage:
    """A cheap blur: down to a handful of pixels and smoothly back up.

    Qt's own blur lives in the graphics-view stack, which means a scene and a
    render pass for what is a background behind a face - this reads the same at
    a fraction of the work.
    """
    small = max(2, size // 22)
    return image.scaled(
        small, small, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    ).scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


class AccountPicture(QObject):
    """lock_screen.account_picture: the avatar above your name when you sign in."""

    def __init__(self, store, theme, wallpaper: Path):
        super().__init__()
        self._store, self._theme, self._wallpaper = store, theme, wallpaper
        self._enabled = False
        self._avatar: QImage | None = None
        self._avatar_for = ""
        self._minutes = 0
        # Redrawn on a timer rather than on a lock, because there is no moment
        # to hook: the sign-in screen reads the file when it draws, and whatever
        # was last written is what you see. A new shape every few minutes means
        # a new shape every time you come back to it.
        self._timer = QTimer(self, singleShot=False, timeout=self.refresh)
        store.changed.connect(self.configure)
        self.configure()

    # ---- settings ----------------------------------------------------------------

    def _section(self) -> dict:
        return (self._store.config.get("lock_screen") or {}).get("account_picture") or {}

    @Slot()
    def configure(self):
        section = self._section()
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
        # Not at once: this reaches the network for an avatar, and nothing about
        # a sign-in picture is urgent while the desk is still opening.
        QTimer.singleShot(20_000, self.refresh)

    # ---- the pieces --------------------------------------------------------------

    def avatar(self) -> QImage | None:
        """Whose face goes in the shape. GitHub serves one per account name."""
        who = str(self._section().get("github") or "").strip().lstrip("@")
        if not who:
            return None
        if self._avatar is not None and self._avatar_for == who:
            return self._avatar
        data = get_bytes(f"https://github.com/{who}.png?size=460", timeout=15)
        if not data:
            print(f"[unidesk] sign-in picture: GitHub has no avatar for {who}")
            return None
        image = QImage()
        if not image.loadFromData(data) or image.isNull():
            return None
        self._avatar, self._avatar_for = image, who
        return image

    def render(self, size: int, shape: str) -> QImage:
        """One picture at one size: the wallpaper, the avatar in a shape, a ring."""
        # Drawn large and scaled down at the end, because a nine-lobed cookie at
        # 32 pixels drawn directly is a staircase however much antialiasing is on.
        big = max(size, 256)
        canvas = QImage(big, big, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(QColor(16, 16, 20))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        wall = QImage(str(self._wallpaper))
        if not wall.isNull():
            scaled = wall.scaled(
                big, big, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
            crop = QRect((scaled.width() - big) // 2, (scaled.height() - big) // 2, big, big)
            behind = _blurred(scaled.copy(crop), big)
            painter.drawImage(QPoint(0, 0), behind)
            # Darkened, so a face reads against it whatever the wallpaper is.
            painter.fillRect(canvas.rect(), QColor(0, 0, 0, 90))

        face = self.avatar()
        if face is not None and not face.isNull():
            inner = int(big * INSET)
            offset = (big - inner) / 2
            path = shape_path(shape, inner)
            path.translate(offset, offset)
            painter.save()
            painter.setClipPath(path)
            fitted = face.scaled(
                inner, inner, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
            painter.drawImage(
                QPoint(int(offset - (fitted.width() - inner) / 2), int(offset - (fitted.height() - inner) / 2)),
                fitted,
            )
            painter.restore()

        painter.end()

        if big == size:
            return canvas
        return canvas.scaled(
            size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

    # ---- where Windows keeps it --------------------------------------------------

    def targets(self) -> dict[int, Path]:
        """The files the registry points at, by size.

        Read every time rather than cached: setting any picture in Settings
        rewrites these paths with a fresh GUID, and a cache that outlived that
        would have unidesk writing files nothing reads any more.
        """
        found: dict[int, Path] = {}
        script = (
            "$sid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value;"
            '$k = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AccountPicture\\Users\\$sid";'
            "if (Test-Path $k) { (Get-ItemProperty $k).PSObject.Properties |"
            " Where-Object { $_.Name -like 'Image*' } |"
            " ForEach-Object { $_.Name + '=' + $_.Value } }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            print(f"[unidesk] sign-in picture: could not read where Windows keeps it: {e}")
            return found
        for line in (result.stdout or "").splitlines():
            name, _, value = line.strip().partition("=")
            if not name.startswith("Image") or not value:
                continue
            try:
                found[int(name[len("Image"):])] = Path(value)
            except ValueError:
                continue
        return found

    @Slot()
    def refresh(self):
        """Draw a new picture and put it where Windows will find it."""
        if not self._enabled:
            return
        wanted = str(self._section().get("shape") or "random")
        shape = wanted if wanted in shape_names() else random.choice(shape_names())

        spare = _home() / "account-picture"
        try:
            spare.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[unidesk] sign-in picture: {e}")
            return

        targets = self.targets()
        written = denied = 0
        for size in SIZES:
            picture = self.render(size, shape)
            # unidesk's own copy always, so there is something to pick by hand
            # even where the grant has not been given.
            picture.save(str(spare / f"account-{size}.jpg"), "JPG", 94)
            target = targets.get(size)
            if target is None:
                continue
            if picture.save(str(target), "JPG", 94):
                written += 1
            else:
                denied += 1

        if written:
            print(f"[unidesk] sign-in picture: {shape}, {written} sizes written")
        elif denied:
            print(
                f"[unidesk] sign-in picture drawn in {spare}, but Windows' own copy is not "
                "writable yet - run tools\\allow-signin-picture.ps1 once as administrator"
            )
        else:
            print(f"[unidesk] sign-in picture drawn in {spare}; Windows has no account picture set")
