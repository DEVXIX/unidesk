"""CPU, memory, disk, GPU (NVIDIA via nvidia-smi), network and uptime."""
from __future__ import annotations

import getpass
import os
import platform
import shutil
import subprocess
import threading
import time
import winreg

import psutil
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

CREATE_NO_WINDOW = 0x08000000


def _cpu_name() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor()


class System(QObject):
    """Exposed to QML as `System`: `System.stats.cpu`, `.ram`, `.gpu.temp`..."""

    statsChanged = Signal()
    _gpu_ready = Signal("QVariant")

    def __init__(self):
        super().__init__()
        self._stats: dict = {
            "cpu": 0.0, "ram": 0.0, "ramUsedGb": 0.0, "ramTotalGb": 0.0, "disk": 0.0, "diskFreeGb": 0.0,
            "gpu": None, "uptime": 0, "user": getpass.getuser(), "host": platform.node(),
            "cpuName": _cpu_name(), "down": 0.0, "up": 0.0, "cpuTemp": None,
        }
        self._tick = 0
        self._timer = QTimer(self, interval=2000, timeout=self._sample)
        self._gpu_ok = shutil.which("nvidia-smi") is not None
        self._gpu_busy = False
        self._net = None
        self._gpu_ready.connect(self._on_gpu)
        psutil.cpu_percent(None)

    def start(self):
        if not self._timer.isActive():
            self._sample()
            self._timer.start()

    def stop(self):
        self._timer.stop()

    @Slot()
    def _sample(self):
        s = self._stats
        s["cpu"] = psutil.cpu_percent(None)
        vm = psutil.virtual_memory()
        s["ram"], s["ramUsedGb"], s["ramTotalGb"] = vm.percent, vm.used / 1024**3, vm.total / 1024**3
        try:
            du = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
            s["disk"], s["diskFreeGb"] = du.percent, du.free / 1024**3
        except OSError:
            pass
        s["uptime"] = int(time.time() - psutil.boot_time())
        io = psutil.net_io_counters()
        now = time.monotonic()
        if self._net:
            dt = now - self._net[2]
            s["down"] = max(0.0, (io.bytes_recv - self._net[0]) / dt)
            s["up"] = max(0.0, (io.bytes_sent - self._net[1]) / dt)
        self._net = (io.bytes_recv, io.bytes_sent, now)
        self._tick += 1
        if self._tick % 5 == 1:
            threading.Thread(target=self._query_cpu_temp, daemon=True).start()
        if self._gpu_ok and not self._gpu_busy:
            self._gpu_busy = True
            threading.Thread(target=self._query_gpu, daemon=True).start()
        self.statsChanged.emit()

    def _query_cpu_temp(self):
        """CPU temperature needs a sensor reader: LibreHardwareMonitor's web server (port 8085), if it runs."""
        import json
        import urllib.request

        try:
            with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=1.5) as res:
                tree = json.loads(res.read().decode("utf-8"))
        except Exception:
            self._stats["cpuTemp"] = None
            return
        found = []

        def walk(node, in_cpu=False):
            text = str(node.get("Text", "")).lower()
            in_cpu = in_cpu or str(node.get("ImageURL", "")).endswith("cpu.png") or "cpu" in text
            if in_cpu and node.get("Type") == "Temperature" and ("package" in text or "tctl" in text):
                try:
                    found.append(float(str(node.get("Value", "")).split()[0].replace(",", ".")))
                except ValueError:
                    pass
            for child in node.get("Children", []):
                walk(child, in_cpu)

        walk(tree)
        self._stats["cpuTemp"] = found[0] if found else None

    def _query_gpu(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4, creationflags=CREATE_NO_WINDOW,
            ).stdout.strip().splitlines()[0]
            load, temp, used, total, *name = [p.strip() for p in out.split(",")]
            gpu = {
                "load": float(load), "temp": float(temp), "vram": 100 * float(used) / float(total),
                "name": ",".join(name).replace("NVIDIA ", "").replace("GeForce ", ""),
            }
        except Exception:
            self._gpu_ok = False
            gpu = None
        self._gpu_ready.emit(gpu)

    @Slot("QVariant")
    def _on_gpu(self, gpu):
        self._gpu_busy = False
        self._stats["gpu"] = gpu

    @Property("QVariantMap", notify=statsChanged)
    def stats(self):
        return self._stats
