"""Battery levels: this PC (if it has one) and connected Bluetooth devices that
report their battery to Windows (headsets, controllers, mice)."""
from __future__ import annotations

import json
import subprocess
import threading

import psutil
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

# DEVPKEY_Bluetooth_Battery
_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in 'Bluetooth','System','HIDClass','AudioEndpoint' } | ForEach-Object {
  $b = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2').Data
  if ($b -ne $null) { [pscustomobject]@{ name = $_.FriendlyName; battery = [int]$b; kind = $_.Class } }
} | Sort-Object name -Unique | ConvertTo-Json -Compress
"""


class Devices(QObject):
    """Exposed to QML as `Devices`: `.items` [{name, battery, kind}], `.pc` (null on desktops)."""

    changed = Signal()
    _ready = Signal("QVariantList")

    def __init__(self):
        super().__init__()
        self._items: list = []
        self._pc = None
        self._timer = QTimer(self, interval=5 * 60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        battery = psutil.sensors_battery()
        self._pc = {"battery": battery.percent, "charging": bool(battery.power_plugged)} if battery else None

        def work():
            try:
                out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                                     capture_output=True, timeout=40, creationflags=0x08000000).stdout.decode("utf-8", "replace")
                data = json.loads(out) if out.strip() else []
                if isinstance(data, dict):
                    data = [data]
            except Exception as e:
                print(f"[unidesk] device batteries failed: {e}")
                data = []
            self._ready.emit([{"name": d.get("name", ""), "battery": int(d.get("battery", 0)), "kind": str(d.get("kind", "")).lower()} for d in data])

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList")
    def _on_ready(self, items):
        self._items = list(items)
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property("QVariant", notify=changed)
    def pc(self):
        return self._pc
