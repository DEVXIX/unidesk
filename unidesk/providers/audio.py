"""Volume mixer: master volume and one slider per app that is making sound (Core Audio via pycaw)."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

ICONS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk" / "icons"


class Audio(QObject):
    """Exposed to QML as `Audio`: `.master`, `.muted`, `.device`, `.sessions`."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self._timer = QTimer(self, interval=1500, timeout=self._sample)
        self._sessions: list[dict] = []
        self._master = 0.0
        self._muted = False
        self._device = ""
        self._endpoint = None
        self._icons: dict[str, str] = {}
        self._names: dict[str, str] = {}

    def start(self):
        if not self._timer.isActive():
            self._sample()
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def _endpoint_volume(self):
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        speakers = AudioUtilities.GetSpeakers()
        device = getattr(speakers, "_dev", speakers)
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self._device = getattr(speakers, "FriendlyName", "") or ""
        return interface.QueryInterface(IAudioEndpointVolume)

    @Slot()
    def _sample(self):
        from pycaw.pycaw import AudioUtilities

        try:
            if self._endpoint is None:
                self._endpoint = self._endpoint_volume()
            self._master = float(self._endpoint.GetMasterVolumeLevelScalar())
            self._muted = bool(self._endpoint.GetMute())
        except Exception:
            self._endpoint = None
        sessions = []
        try:
            for s in AudioUtilities.GetAllSessions():
                proc = s.Process
                if proc is None:
                    continue
                try:
                    exe = proc.exe()
                except Exception:
                    exe = ""
                pid = proc.pid
                sessions.append({
                    "pid": pid, "name": self._name(exe, proc.name()), "icon": self._icon(exe),
                    "volume": float(s.SimpleAudioVolume.GetMasterVolume()), "muted": bool(s.SimpleAudioVolume.GetMute()),
                    "active": s.State == 1,
                })
        except Exception as e:
            print(f"[unidesk] audio sessions failed: {e}")
        # one row per app even if it opened several sessions
        merged: dict[str, dict] = {}
        for s in sessions:
            merged.setdefault(s["name"], s)
        sessions = sorted(merged.values(), key=lambda s: (not s["active"], s["name"].lower()))
        state = (sessions, self._master, self._muted)
        if state != getattr(self, "_last_state", None):
            self._last_state = state
            self._sessions = sessions
            self.changed.emit()

    def _name(self, exe: str, fallback: str) -> str:
        if exe not in self._names:
            from ..dock import winapi

            self._names[exe] = (winapi.file_description(exe) if exe else "") or Path(fallback).stem.capitalize()
        return self._names[exe]

    def _icon(self, exe: str) -> str:
        if not exe:
            return ""
        if exe not in self._icons:
            from ..dock import winapi

            try:
                path = winapi.icon_png(exe, 64, ICONS)
            except Exception:
                path = ""
            self._icons[exe] = QUrl.fromLocalFile(path).toString() if path else ""
        return self._icons[exe]

    def _session(self, pid: int):
        from pycaw.pycaw import AudioUtilities

        return [s for s in AudioUtilities.GetAllSessions() if s.Process and s.Process.pid == pid]

    @Property(float, notify=changed)
    def master(self):
        return self._master

    @Property(bool, notify=changed)
    def muted(self):
        return self._muted

    @Property(str, notify=changed)
    def device(self):
        return self._device

    @Property("QVariantList", notify=changed)
    def sessions(self):
        return self._sessions

    @Slot(float)
    def setMaster(self, value: float):
        if self._endpoint is not None:
            self._endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, value)), None)
            self._sample()

    @Slot()
    def toggleMute(self):
        if self._endpoint is not None:
            self._endpoint.SetMute(not self._muted, None)
            self._sample()

    @Slot(int, float)
    def setVolume(self, pid: int, value: float):
        for s in self._session(pid):
            s.SimpleAudioVolume.SetMasterVolume(max(0.0, min(1.0, value)), None)
        self._sample()

    @Slot(int)
    def toggleAppMute(self, pid: int):
        for s in self._session(pid):
            s.SimpleAudioVolume.SetMute(not s.SimpleAudioVolume.GetMute(), None)
        self._sample()

    @Slot()
    def openSoundSettings(self):
        os.startfile("ms-settings:sound")
