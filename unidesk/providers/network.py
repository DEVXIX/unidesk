"""Network speed: download and upload across the real network adapters
(loopback and virtual switches left out), sampled every second, with the
last minute kept for a graph."""
from __future__ import annotations

import time

import psutil
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

HISTORY = 60
# Adapters whose traffic is local or double-counted.
_VIRTUAL = ("loopback", "vethernet", "bluetooth", "isatap", "teredo", "6to4", "npcap", "vmware", "virtualbox", "hyper-v", "wsl")


def _counted(name: str) -> bool:
    lowered = name.lower()
    return not any(word in lowered for word in _VIRTUAL)


class Network(QObject):
    """Exposed to QML as `Network`: `Network.stats.down` / `.up` in bytes per
    second, `.downHistory` / `.upHistory` (oldest first), `.adapter`, `.kind`."""

    statsChanged = Signal()

    def __init__(self):
        super().__init__()
        self._stats: dict = {"down": 0.0, "up": 0.0, "downHistory": [], "upHistory": [], "adapter": "", "kind": "lan"}
        self._last: dict[str, tuple[int, int]] = {}  # adapter -> (received, sent) at the last sample
        self._last_at = 0.0
        self._timer = QTimer(self, interval=1000, timeout=self._sample)

    def start(self):
        if not self._timer.isActive():
            self._last = {}
            self._sample()
            self._timer.start()

    def stop(self):
        self._timer.stop()

    @Slot()
    def _sample(self):
        try:
            counters = psutil.net_io_counters(pernic=True)
            links = psutil.net_if_stats()
        except (OSError, RuntimeError):
            return
        names = [n for n, link in links.items() if link.isup and n in counters and _counted(n)]
        now = time.monotonic()
        s = self._stats
        if self._last:
            # Per adapter, so one that just connected (Wi-Fi back, waking from sleep)
            # doesn't add its whole lifetime of traffic as a single second.
            received = sum(max(0, counters[n].bytes_recv - self._last[n][0]) for n in names if n in self._last)
            sent = sum(max(0, counters[n].bytes_sent - self._last[n][1]) for n in names if n in self._last)
            elapsed = max(0.001, now - self._last_at)
            s["down"], s["up"] = received / elapsed, sent / elapsed
            s["downHistory"] = (s["downHistory"] + [s["down"]])[-HISTORY:]
            s["upHistory"] = (s["upHistory"] + [s["up"]])[-HISTORY:]
        self._last = {n: (counters[n].bytes_recv, counters[n].bytes_sent) for n in names}
        self._last_at = now
        wireless = [n for n in names if any(w in n.lower() for w in ("wi-fi", "wlan", "wireless"))]
        s["adapter"] = (wireless or names or [""])[0]
        s["kind"] = "off" if not names else "wifi" if wireless else "lan"
        self.statsChanged.emit()

    @Property("QVariantMap", notify=statsChanged)
    def stats(self):
        return self._stats
