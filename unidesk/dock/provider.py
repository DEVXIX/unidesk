"""The dock's data: pinned + running apps (with icons and names), keyboard
language, network state, and actions (focus, launch, close, pin, Start...).

Window changes arrive through WinEvent hooks (debounced), with a slow poll as
a safety net, so an idle desktop costs next to nothing."""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

import psutil
from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from . import winapi
from .showdesktop import ShowDesktop

ICONS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk" / "icons"
PINNED_LNK = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar"

WinEventProc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
winapi.user32.SetWinEventHook.restype = wintypes.HANDLE
winapi.user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, WinEventProc, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
winapi.user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND = 0x0016, 0x0017
EVENT_OBJECT_DESTROY, EVENT_OBJECT_SHOW, EVENT_OBJECT_HIDE = 0x8001, 0x8002, 0x8003
EVENT_OBJECT_NAMECHANGE = 0x800C
EVENT_OBJECT_CLOAKED, EVENT_OBJECT_UNCLOAKED = 0x8017, 0x8018


def app_key(exe: str, aumid: str) -> str:
    return f"aumid:{aumid}" if aumid else f"exe:{exe.lower()}"


def _resolve_lnk(path: Path) -> str:
    try:
        import pylnk3

        target = pylnk3.parse(str(path)).path
        return os.path.expandvars(target) if target else ""
    except Exception:
        return ""


def taskbar_pins() -> list[dict]:
    """The Windows taskbar's own pins, in order: shortcuts from the User Pinned
    folder and Store apps (by AppUserModelId), read from the Taskband "Favorites" registry value."""
    import re
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband") as key:
            blob = winreg.QueryValueEx(key, "Favorites")[0]
    except OSError:
        blob = b""
    # The blob is binary shell item lists; the readable parts are UTF-16 strings.
    text = "\n".join(m.group(0).decode("utf-16-le") for m in re.finditer(rb"(?:[\x20-\x7e]\x00){4,}", blob))

    found: list[tuple[int, dict]] = []
    lnks = sorted(PINNED_LNK.glob("*.lnk")) if PINNED_LNK.exists() else []
    for lnk in lnks:
        at = text.find(lnk.name)
        exe = _resolve_lnk(lnk)
        if not exe or "%" in exe:
            # Shell shortcuts (File Explorer) have no plain target.
            exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe") if "explorer" in lnk.stem.lower() else ""
        found.append((at if at >= 0 else 10**9, {"name": lnk.stem, "lnk": str(lnk), "exe": exe}))
    seen = set()
    for m in re.finditer(r"[A-Za-z0-9.\-]+_[a-z0-9]{13}![A-Za-z0-9.\-_]+", text):
        if m.group(0) not in seen:
            seen.add(m.group(0))
            found.append((m.start(), {"aumid": m.group(0)}))
    return [pin for _, pin in sorted(found, key=lambda f: f[0])]


class Dock(QObject):
    """Exposed to QML as `Dock`."""

    appsChanged = Signal()
    statusChanged = Signal()
    _icon_ready = Signal(str, str)
    _name_ready = Signal(str, str)
    _badges_ready = Signal("QVariantList")

    def __init__(self, store):
        super().__init__()
        self._store = store
        self._apps: list[dict] = []
        self._windows: list[dict] = []
        self._icons: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._pending: set[str] = set()
        self._language = ""
        self._network = "lan"
        self._hooks = []
        self._running = False
        self._generation = 0
        self._own_pid = os.getpid()
        # The same list the dock draws its apps from, so what gets cleared is
        # exactly what has a place on the dock - and never unidesk's own windows.
        self._show_desktop = ShowDesktop(
            windows=lambda: winapi.app_windows(self._own_pid),
            minimize=winapi.minimize_quietly,
            restore=winapi.restore,
            is_minimized=winapi.is_minimized,
            exists=winapi.exists,
            activate=winapi.activate,
        )
        # Set by the app: the desk looks again at once, rather than when the
        # next event or its one-second poll gets round to it.
        self.after_show_desktop = None
        self._docks: list = []                     # one dock window per screen
        self._reserved: dict[int, tuple] = {}      # dock hwnd -> (monitor, height in physical px) it reserved
        self._wanted: dict[int, tuple] = {}        # dock hwnd -> (window, logical height), to re-apply
        self._thumbs: dict[int, winapi.Thumbnails] = {}
        self._tray = 0
        self._autohide_before: bool | None = None
        self._ghosted = False
        self._badges: list[dict] = []
        self.suspended = False
        # Apps just launched from the dock: bring their first window forward
        # (Windows opens them behind the current window otherwise).
        self._launching: dict[str, float] = {}

        self._debounce = QTimer(self, singleShot=True, interval=120, timeout=self.refresh)
        self._poll = QTimer(self, interval=4000, timeout=self.refresh)
        self._status = QTimer(self, interval=2000, timeout=self._update_status)
        self._badges_ready.connect(self._on_badges)
        self._keep_hidden = QTimer(self, interval=3000, timeout=self._apply_taskbar)
        store.changed.connect(self._on_config)
        self._icon_ready.connect(self._on_icon)
        self._name_ready.connect(self._on_name)
        self._worker_queue: list[tuple[str, str, str]] = []
        self._worker_lock = threading.Condition()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- config ----------------------------------------------------------------

    @property
    def settings(self) -> dict:
        return self._store.config.get("dock") or {}

    def _pinned(self) -> list[dict]:
        pinned = self.settings.get("pinned")
        return pinned if isinstance(pinned, list) else []

    def seed_pins(self, force: bool = False):
        """First run (or on request): copy the Windows taskbar's pins, in order."""
        if isinstance(self.settings.get("pinned"), list) and not force:
            return
        pins = taskbar_pins()
        self._store.set_setting("dock.pinned", pins)

    @Slot()
    def importTaskbarPins(self):
        self.seed_pins(force=True)
        QTimer.singleShot(50, self.refresh)

    # ---- lifecycle -------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    def start(self, passive: bool = False):
        """passive: read apps only (snapshot tests) - no hooks, pins or taskbar changes."""
        if self._running:
            return
        self._running = True
        self._generation += 1
        winapi.com_init()
        if passive:
            self.refresh()
            return
        # Before seed_pins(): saving the pins reapplies the taskbar settings, which turns auto-hide off.
        self._autohide_before = winapi.taskbar_autohide()
        self.seed_pins()
        self._proc = WinEventProc(lambda *_: self._debounce.start())
        for low, high in ((EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND), (EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND),
                          (EVENT_OBJECT_DESTROY, EVENT_OBJECT_HIDE), (EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_NAMECHANGE),
                          (EVENT_OBJECT_CLOAKED, EVENT_OBJECT_UNCLOAKED)):
            hook = winapi.user32.SetWinEventHook(low, high, None, self._proc, 0, 0, 0x0002)  # OUTOFCONTEXT | SKIPOWNPROCESS
            if hook:
                self._hooks.append(hook)
        self._poll.start()
        self._status.start()
        self._update_status()
        self.refresh()
        self._apply_taskbar()
        self._keep_hidden.start()
        threading.Thread(target=self._badge_loop, daemon=True).start()

    def _apply_taskbar(self):
        """Keep the real taskbars invisible and click-through (not hidden: a hidden
        taskbar stops reporting badges): the main one, and the other screens' ones
        when those have a dock too. Explorer sometimes undoes it; redo it."""
        tray = winapi.main_tray()
        if tray and tray != self._tray:
            restarted = bool(self._tray)
            self._tray = tray
            if restarted:  # Explorer restarted and forgot the docks' reserved space; let it settle first
                QTimer.singleShot(1500, self._reserve_again)
        self._reapply_reservations()  # a dock that moved screens reserves on its new one
        want = bool(self.settings.get("enabled", True)) and bool(self.settings.get("hide_windows_taskbar", True))
        if want:
            if winapi.taskbar_autohide():
                winapi.set_taskbar_autohide(False)  # auto-hide would slide it back in over the dock
            winapi.ghost_taskbars(main=True, secondary=self.settings.get("all_screens", True) is not False)
            self._ghosted = True
        elif self._ghosted:
            winapi.ghost_taskbar(False)
            if self._autohide_before:
                winapi.set_taskbar_autohide(True)
            self._ghosted = False

    def _on_config(self):
        if self._running:
            self._apply_taskbar()
            self._debounce.start()

    def _badge_loop(self):
        import time

        try:
            reader = winapi.BadgeReader()
        except Exception as e:
            print(f"[unidesk] badges unavailable: {e}")
            return
        last = None
        generation = self._generation
        while self._running and generation == self._generation:
            if not self.suspended and self.settings.get("badges", True):
                try:
                    badges = reader.read()
                except Exception:
                    badges = []
                if badges != last:
                    last = badges
                    self._badges_ready.emit(badges)
            time.sleep(2.5)

    @Slot("QVariantList")
    def _on_badges(self, badges):
        self._badges = list(badges)
        self._debounce.start()

    def _badge_for(self, app: dict) -> int:
        names = {str(app.get("name") or "").lower()}
        if app.get("lnk"):
            names.add(Path(app["lnk"]).stem.lower())
        for b in self._badges:
            if (app.get("aumid") and b["appid"] == app["aumid"]) or b["name"].lower() in names:
                return int(b["count"])
        return 0

    def stop(self):
        self._keep_hidden.stop()
        if self._ghosted:
            winapi.ghost_taskbar(False)
            if self._autohide_before:
                winapi.set_taskbar_autohide(True)
            self._ghosted = False
        for hook in self._hooks:
            winapi.user32.UnhookWinEvent(hook)
        self._hooks.clear()
        self._poll.stop()
        self._status.stop()
        for hwnd in list(self._reserved):
            winapi.release_reservation(hwnd)
        self._reserved.clear()
        for thumbs in self._thumbs.values():
            thumbs.clear()
        self._running = False

    # ---- dock windows (one per screen) -----------------------------------------------

    @Slot(QObject)
    def registerWindow(self, window):
        if not any(w is window for w in self._docks):
            self._docks.append(window)
        if os.environ.get("UNIDESK_SNAPSHOT"):
            return
        hwnd = int(window.winId())
        winapi.set_noactivate(hwnd)
        winapi.keep_on_top(hwnd)

    def forget_window(self, window):
        """A dock window is closing (its screen went away, or the dock was turned off)."""
        if not any(w is window for w in self._docks):
            return
        self._docks = [w for w in self._docks if w is not window]
        hwnd = int(window.winId())
        if self._reserved.pop(hwnd, None) is not None:
            winapi.release_reservation(hwnd)
        self._wanted.pop(hwnd, None)
        thumbs = self._thumbs.pop(hwnd, None)
        if thumbs is not None:
            thumbs.clear()

    @Slot(QObject, "QVariantList")
    def showThumbnails(self, window, items):
        """[{hwnd, x, y, w, h}] in the dock window's logical pixels."""
        hwnd = int(window.winId())
        thumbs = self._thumbs.setdefault(hwnd, winapi.Thumbnails())
        ratio = window.devicePixelRatio()
        rows = [(int(i["hwnd"]), int(i["x"] * ratio), int(i["y"] * ratio), int(i["w"] * ratio), int(i["h"] * ratio)) for i in items]
        thumbs.show(hwnd, rows)

    @Slot(QObject)
    def clearThumbnails(self, window):
        thumbs = self._thumbs.get(int(window.winId()))
        if thumbs is not None:
            thumbs.clear()

    @Slot(int)
    def closeWindow(self, hwnd: int):
        winapi.close(hwnd)
        QTimer.singleShot(400, self.refresh)

    @Slot(QObject, bool)
    def setActivatable(self, window, on: bool):
        hwnd = int(window.winId())
        ex = winapi.user32.GetWindowLongPtrW(hwnd, winapi.GWL_EXSTYLE)
        ex = ex & ~winapi.WS_EX_NOACTIVATE if on else ex | winapi.WS_EX_NOACTIVATE
        winapi.user32.SetWindowLongPtrW(hwnd, winapi.GWL_EXSTYLE, ex)

    @Slot(QObject, int)
    def reserve(self, window, height: int):
        """Keep maximised windows above the dock on its screen (like the real taskbar does)."""
        if os.environ.get("UNIDESK_SNAPSHOT"):
            return
        hwnd = int(window.winId())
        self._wanted[hwnd] = (window, height)
        if not self.settings.get("reserve_space", True):
            if self._reserved.pop(hwnd, None) is not None:
                winapi.release_reservation(hwnd)
            return
        # Keyed by monitor too: a dock window can be created before it is moved onto its screen.
        placed = (winapi.window_monitor(hwnd), int(round(height * window.devicePixelRatio())))
        if self._reserved.get(hwnd) == placed:
            return
        self._reserved[hwnd] = placed
        winapi.reserve_bottom(hwnd, placed[1])

    def _reapply_reservations(self):
        for window, height in list(self._wanted.values()):
            self.reserve(window, height)

    def _reserve_again(self):
        """Reserve from scratch (Explorer's list of reserved space was lost)."""
        self._reserved.clear()
        self._reapply_reservations()

    # ---- apps --------------------------------------------------------------------

    @Slot()
    def refresh(self):
        if not self._running:
            return
        windows = winapi.app_windows(self._own_pid)
        fg = winapi.foreground()
        groups: dict[str, dict] = {}
        order: list[str] = []

        for pin in self._pinned():
            exe, aumid = str(pin.get("exe") or ""), str(pin.get("aumid") or "")
            key = app_key(exe, aumid) if (exe or aumid) else f"lnk:{pin.get('lnk', '')}"
            if key in groups:
                continue
            groups[key] = {"key": key, "name": str(pin.get("name") or ""), "exe": exe, "aumid": aumid,
                           "lnk": str(pin.get("lnk") or ""), "pinned": True, "windows": []}
            order.append(key)

        for w in windows:
            key = self._pin_for(w, groups) or app_key(w["exe"], w["aumid"])
            if key not in groups:
                groups[key] = {"key": key, "name": "", "exe": w["exe"], "aumid": w["aumid"], "lnk": "", "pinned": False, "windows": []}
                order.append(key)
            groups[key]["windows"].append({"hwnd": w["hwnd"], "title": w["title"], "minimized": w["minimized"],
                                           "monitor": w["monitor"], "active": w["hwnd"] == fg})

        now = time.monotonic()
        for key, started in list(self._launching.items()):
            group = groups.get(key)
            if group and group["windows"]:
                del self._launching[key]
                hwnd = group["windows"][0]["hwnd"]
                QTimer.singleShot(0, lambda h=hwnd: winapi.activate(h))
            elif now - started > 20:
                del self._launching[key]

        apps = []
        for key in order:
            g = groups[key]
            if not g["pinned"] and not g["windows"]:
                continue
            g["running"] = bool(g["windows"])
            g["active"] = any(w["hwnd"] == fg for w in g["windows"])
            g["icon"] = self._icons.get(key, "")
            g["name"] = g["name"] or self._names.get(key) or (g["windows"][0]["title"] if g["windows"] else Path(g["exe"]).stem)
            g["badge"] = self._badge_for(g)
            g["launching"] = key in self._launching
            if key not in self._icons or key not in self._names:
                self._request(key, g)
            apps.append(g)

        self._windows = windows
        if apps != self._apps:
            self._apps = apps
            self.appsChanged.emit()

    @staticmethod
    def _pin_for(window: dict, groups: dict) -> str:
        """Match a window to a pin whose shortcut targets a launcher in the app's
        folder (Discord's pin runs Update.exe, the window belongs to Discord.exe)."""
        exe = window["exe"].lower()
        for key, g in groups.items():
            if not g["pinned"] or not g["exe"] or g["aumid"]:
                continue
            pin_exe = g["exe"].lower()
            if pin_exe == exe:
                return key
            folder = os.path.dirname(pin_exe) + "\\"
            stem = Path(g["lnk"]).stem.lower() if g["lnk"] else ""
            if exe.startswith(folder) and (os.path.basename(pin_exe) == "update.exe" or (stem and stem in Path(exe).stem.lower())):
                return key
        return ""

    def _request(self, key: str, app: dict):
        if key in self._pending:
            return
        self._pending.add(key)
        source = f"shell:AppsFolder\\{app['aumid']}" if app["aumid"] else (app["lnk"] or app["exe"])
        with self._worker_lock:
            self._worker_queue.append((key, source, app["exe"]))
            self._worker_lock.notify()

    def _worker(self):
        winapi.com_init()
        while True:
            with self._worker_lock:
                while not self._worker_queue:
                    self._worker_lock.wait()
                key, source, exe = self._worker_queue.pop(0)
            try:
                icon = winapi.icon_png(source, 96, ICONS) if source else ""
            except Exception:
                icon = ""
            if not icon and exe and exe != source:
                try:
                    icon = winapi.icon_png(exe, 96, ICONS)
                except Exception:
                    icon = ""
            name = ""
            if source.startswith("shell:AppsFolder"):
                name = winapi.shell_display_name(source)
            if not name and exe:
                name = winapi.file_description(exe)
            self._icon_ready.emit(key, QUrl.fromLocalFile(icon).toString() if icon else "")
            self._name_ready.emit(key, name)

    @Slot(str, str)
    def _on_icon(self, key: str, url: str):
        self._icons[key] = url
        self._debounce.start()

    @Slot(str, str)
    def _on_name(self, key: str, name: str):
        self._names[key] = name
        self._debounce.start()

    def _find(self, key: str) -> dict | None:
        return next((a for a in self._apps if a["key"] == key), None)

    # ---- jump list -------------------------------------------------------------

    @Slot(str, result="QVariantList")
    def jumpList(self, key: str) -> list:
        """What Windows would show on a right-click: the app's own tasks, then
        the files and folders it opened lately. Empty for an app that publishes
        neither, which is most of them."""
        app = self._find(str(key))
        if not app:
            return []
        from .. import jumplist

        try:
            return jumplist.entries(app.get("exe") or "", app.get("aumid") or "")
        except Exception as e:  # a missing jump list must never break the menu
            print(f"[unidesk] jump list for {key}: {e}")
            return []

    @Slot(str, str)
    def openJumpItem(self, target: str, args: str):
        """Run one jump-list row the way Explorer runs it."""
        from .. import jumplist

        if not jumplist.open_entry(str(target), str(args)):
            print(f"[unidesk] could not open {target} {args}")

    # ---- status (language, network) --------------------------------------------

    def _update_status(self):
        language = winapi.keyboard_language()
        stats = psutil.net_if_stats()
        up = [name for name, s in stats.items() if s.isup and not name.lower().startswith(("loopback", "vethernet", "bluetooth"))]
        network = "off" if not up else "wifi" if any("wi-fi" in n.lower() or "wlan" in n.lower() or "wireless" in n.lower() for n in up) else "lan"
        if (language, network) != (self._language, self._network):
            self._language, self._network = language, network
            self.statusChanged.emit()

    # ---- QML: data ----------------------------------------------------------------

    @Property("QVariantList", notify=appsChanged)
    def apps(self):
        return self._apps

    @Property(str, notify=statusChanged)
    def language(self):
        return self._language

    @Property(str, notify=statusChanged)
    def network(self):
        return self._network

    # ---- QML: actions -------------------------------------------------------------

    @Slot(str, str)
    def click(self, key: str, monitor: str):
        """Focus the app; minimise it if it is already in front; cycle its windows.
        monitor: only that screen's windows count (a dock showing just its screen's apps)."""
        app = self._find(key)
        if not app:
            return
        windows = [w for w in app["windows"] if not monitor or w["monitor"] == monitor]
        if not windows:
            self.launch(key)
            return
        fg = winapi.foreground()
        hwnds = [w["hwnd"] for w in windows]
        if fg in hwnds:
            if len(hwnds) == 1:
                winapi.minimize(fg)
            else:
                winapi.activate(hwnds[(hwnds.index(fg) + 1) % len(hwnds)])
        else:
            winapi.activate(hwnds[0])
        QTimer.singleShot(150, self.refresh)

    @Slot(int)
    def focusWindow(self, hwnd: int):
        winapi.activate(hwnd)

    @Slot(str)
    def launch(self, key: str):
        app = self._find(key)
        if not app:
            print(f"[unidesk] launch: no app for {key}")
            return
        winapi.user32.AllowSetForegroundWindow(-1)  # let what we start take the foreground
        try:
            if app["aumid"]:
                target = "shell:AppsFolder\\" + app["aumid"]
                os.startfile(target)
            elif app["lnk"] and Path(app["lnk"]).exists():
                target = app["lnk"]
                os.startfile(target)
            elif app["exe"] and Path(app["exe"]).exists():
                target = app["exe"]
                subprocess.Popen([target], cwd=str(Path(target).parent), creationflags=0x00000008 | 0x00000200)
            else:
                print(f"[unidesk] launch: nothing to start for {app['name']!r}")
                return
        except OSError as e:
            print(f"[unidesk] could not launch {app['name']!r}: {e}")
            return
        print(f"[unidesk] launched {app['name']!r} via {target}")
        self._launching[key] = time.monotonic()
        self._debounce.start()
        # Poll a little faster while waiting for its window.
        for delay in (500, 1200, 2500, 4000, 7000):
            QTimer.singleShot(delay, self.refresh)

    @Slot(str, str)
    def closeApp(self, key: str, monitor: str):
        app = self._find(key)
        for w in (app or {}).get("windows", []):
            if not monitor or w["monitor"] == monitor:
                winapi.close(w["hwnd"])

    @Slot(str, bool)
    def setPinned(self, key: str, pinned: bool):
        app = self._find(key)
        if not app:
            return
        pins = [dict(p) for p in self._pinned()]
        match = lambda p: app_key(str(p.get("exe") or ""), str(p.get("aumid") or "")) == key or f"lnk:{p.get('lnk', '')}" == key
        pins = [p for p in pins if not match(p)]
        if pinned:
            entry = {"name": app["name"], "exe": app["exe"]}
            if app["aumid"]:
                entry["aumid"] = app["aumid"]
            if app["lnk"]:
                entry["lnk"] = app["lnk"]
            pins.append(entry)
        self._store.set_setting("dock.pinned", pins)
        QTimer.singleShot(50, self.refresh)

    @Slot(str, int)
    def movePinned(self, key: str, index: int):
        pins = [dict(p) for p in self._pinned()]
        keys = [app_key(str(p.get("exe") or ""), str(p.get("aumid") or "")) if (p.get("exe") or p.get("aumid")) else f"lnk:{p.get('lnk', '')}" for p in pins]
        if key not in keys:
            return
        pin = pins.pop(keys.index(key))
        pins.insert(max(0, min(index, len(pins))), pin)
        self._store.set_setting("dock.pinned", pins)
        QTimer.singleShot(50, self.refresh)

    @Slot()
    def showDesktop(self):
        """Clear the desk down to the wallpaper and the widgets, or bring it back.

        Not Win+D. Windows' version decides for itself what the desktop is, and
        the widgets only come along while Qt has left their window owned by
        Progman; this one minimises the apps and nothing else, so the widgets
        never go anywhere to begin with.
        """
        self._show_desktop.toggle()
        # A game that was full screen is minimised now: the widgets on its
        # screen were idled for it, and should come back straight away.
        if self.after_show_desktop:
            QTimer.singleShot(60, self.after_show_desktop)
        QTimer.singleShot(120, self.refresh)

    @Slot()
    def openStart(self):
        winapi.tap(winapi.VK_LWIN)

    @Slot()
    def openSearch(self):
        winapi.tap(winapi.VK_LWIN, ord("S"))

    @Slot()
    def openQuickSettings(self):
        winapi.tap(winapi.VK_LWIN, ord("A"))

    @Slot()
    def openNotifications(self):
        winapi.tap(winapi.VK_LWIN, ord("N"))

    @Slot()
    def openTray(self):
        """The real hidden-icons tray (Discord, Steam, ...)."""
        winapi.tap(winapi.VK_LWIN, ord("B"))
        QTimer.singleShot(250, lambda: winapi.tap(0x0D))

    @Slot()
    def switchLanguage(self):
        winapi.tap(winapi.VK_LWIN, 0x20)
        QTimer.singleShot(400, self._update_status)

    @Slot(int)
    def volume(self, steps: int):
        key = 0xAF if steps > 0 else 0xAE
        for _ in range(min(10, abs(steps))):
            winapi.tap(key)

    @Slot()
    def openSettings(self):
        os.startfile("ms-settings:")
