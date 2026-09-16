"""Self-update from GitHub Releases (no server needed).

The installed app checks the repo's latest release a few seconds after start
and then every 6 hours. When a newer version exists it offers it (tray
message + banner); installing downloads the setup .exe, runs it silently, and
the installer starts the new version. Source checkouts only check, never
install: update those with git."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from . import __version__
from .providers.net import _CONTEXT, USER_AGENT

REPO = "DEVXIX/unidesk"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def _parse(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3]) or (0,)


class Updater(QObject):
    """Exposed to QML as `Updater`."""

    changed = Signal()
    _found = Signal("QVariant")
    _progress = Signal(float)
    _downloaded = Signal(str)
    _failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._available: dict | None = None
        self._state = "idle"  # idle | available | downloading | installing | error
        self._progress_value = 0.0
        self._error = ""
        self._found.connect(self._on_found)
        self._progress.connect(self._on_progress)
        self._downloaded.connect(self._on_downloaded)
        self._failed.connect(self._on_failed)
        self._timer = QTimer(self, interval=6 * 3600 * 1000, timeout=self.check)
        self.notify = None  # callable(title, text), set by the app for tray messages

    def start(self):
        QTimer.singleShot(15000, self.check)
        self._timer.start()

    @property
    def can_install(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    # ---- checking --------------------------------------------------------------

    @Slot()
    def check(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            req = urllib.request.Request(LATEST, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=15, context=_CONTEXT) as res:
                release = json.loads(res.read().decode("utf-8"))
        except Exception as e:
            print(f"[unidesk] update check failed: {e}")
            return
        tag = str(release.get("tag_name") or "")
        if _parse(tag) <= _parse(__version__):
            return
        asset = next((a for a in release.get("assets") or [] if str(a.get("name", "")).lower().endswith(".exe")), None)
        if not asset:
            return
        self._found.emit({
            "version": tag.lstrip("v"),
            "notes": str(release.get("body") or "").strip(),
            "url": asset["browser_download_url"],
            "size": int(asset.get("size") or 0),
            "page": release.get("html_url", f"https://github.com/{REPO}/releases"),
        })

    @Slot("QVariant")
    def _on_found(self, info):
        already = self._available and self._available.get("version") == info["version"]
        self._available = info
        if self._state in ("idle", "error"):
            self._state = "available"
        self.changed.emit()
        if not already and self.notify:
            self.notify("unidesk update", f"Version {info['version']} is available. Open the tray menu to install it.")

    # ---- installing ------------------------------------------------------------

    @Slot()
    def install(self):
        if not self._available or self._state in ("downloading", "installing"):
            return
        if not self.can_install:
            os.startfile(self._available["page"])
            return
        self._state, self._progress_value, self._error = "downloading", 0.0, ""
        self.changed.emit()
        threading.Thread(target=self._download, args=(dict(self._available),), daemon=True).start()

    def _download(self, info: dict):
        target = Path(tempfile.gettempdir()) / f"unidesk-setup-{info['version']}.exe"
        try:
            req = urllib.request.Request(info["url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60, context=_CONTEXT) as res, open(target, "wb") as out:
                total = int(res.headers.get("Content-Length") or info.get("size") or 0)
                done = 0
                while chunk := res.read(256 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        self._progress.emit(done / total)
            if info.get("size") and target.stat().st_size != info["size"]:
                raise RuntimeError("download was incomplete")
        except Exception as e:
            self._failed.emit(str(e))
            return
        self._downloaded.emit(str(target))

    @Slot(float)
    def _on_progress(self, value: float):
        self._progress_value = value
        self.changed.emit()

    @Slot(str)
    def _on_failed(self, message: str):
        self._state, self._error = "error", message
        print(f"[unidesk] update failed: {message}")
        self.changed.emit()

    @Slot(str)
    def _on_downloaded(self, path: str):
        self._state = "installing"
        self.changed.emit()
        # The installer closes unidesk (which restores the taskbar), installs
        # over the top keeping settings, and starts the new version.
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         creationflags=0x00000008 | 0x00000200)
        from PySide6.QtWidgets import QApplication

        QTimer.singleShot(800, QApplication.quit)

    # ---- QML -------------------------------------------------------------------

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def version(self):
        return (self._available or {}).get("version", "")

    @Property(str, notify=changed)
    def notes(self):
        return (self._available or {}).get("notes", "")

    @Property(float, notify=changed)
    def progress(self):
        return self._progress_value

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, constant=True)
    def current(self):
        return __version__
