"""Drives and how full they are: fixed disks, plus removable ones with
something in them. Read in the background every half minute."""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

import psutil
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]


def _label(root: str) -> str:
    buf = ctypes.create_unicode_buffer(261)
    if kernel32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0):
        return buf.value
    return ""


def read_drives() -> list[dict]:
    drives = []
    for part in psutil.disk_partitions(all=False):
        opts = part.opts.lower()
        if "cdrom" in opts or not part.fstype:
            continue  # optical drives, and card readers with no card
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        root = part.mountpoint
        drives.append({
            "root": root, "letter": root.rstrip("\\"), "label": _label(root), "fs": part.fstype,
            "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.percent,
            "removable": "removable" in opts,
        })
    return drives


class Storage(QObject):
    """Exposed to QML as `Storage`: `Storage.drives` = [{root, letter, label,
    total, used, free (bytes), percent, removable}], and `open(root)`."""

    drivesChanged = Signal()
    _ready = Signal("QVariantList")

    def __init__(self):
        super().__init__()
        self._drives: list[dict] = []
        self._busy = False
        self._timer = QTimer(self, interval=30_000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        if self._busy:
            return
        self._busy = True

        def work():
            try:
                drives = read_drives()
            except Exception as e:
                print(f"[unidesk] storage failed: {e}")
                drives = []
            self._ready.emit(drives)

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList")
    def _on_ready(self, drives):
        self._busy = False
        drives = list(drives)
        if drives != self._drives:
            self._drives = drives
            self.drivesChanged.emit()

    @Property("QVariantList", notify=drivesChanged)
    def drives(self):
        return self._drives

    @Slot(str)
    def open(self, root: str):
        """Open a drive in File Explorer (only drives this widget lists)."""
        if any(d["root"] == root for d in self._drives):
            os.startfile(root)
