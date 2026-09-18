"""unidesk: YASB-style desktop widgets in Qt Quick.

Every monitor gets one transparent window over its usable area, clipped to
its widgets and pinned to the desktop layer, and a dock.
Everything visual lives in qml/; this file wires config, theme and data
providers together and owns the tray, edit mode and idle-while-gaming."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import winreg
from ctypes import wintypes
from pathlib import Path

import psutil
from PySide6.QtCore import QAbstractNativeEventFilter, Property, QObject, QPoint, QRect, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFontDatabase, QIcon, QImage, QPainter, QPixmap, QRegion
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import desktop, layout, sharing
from .appthemes import AppThemes
from .config import CONFIG_DIR, CONFIG_FILE, ConfigStore
from .displays import Displays
from .dock.provider import Dock
from .captionbuttons import CaptionButtons
from .accountpicture import AccountPicture
from .lockscreen import LockScreen
from .frames import WindowFrames
from .search import Search
from .updater import Updater
from .providers.clipboard import Clipboard, ClipboardImages
from .providers.github import GitHub
from .providers.media import Media
from .providers.audio import Audio
from .providers.devdash import DevDash
from .providers.devices import Devices
from .providers.xd import XD
from .providers.games import Games
from .providers.league import League
from .providers.network import Network
from .providers.notes import Notes
from .providers.notifications import Notifications
from .providers.storage import Storage
from .providers.system import System
from .providers.weather import Weather
from .theme import Theme

HERE = Path(__file__).resolve().parent
WALLPAPER = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# UNIDESK_SNAPSHOT=out.png: render off-screen, save a composite picture, quit.
SNAPSHOT = os.environ.get("UNIDESK_SNAPSHOT", "")
INSTANCE = "unidesk-snapshot" if SNAPSHOT else "unidesk-single-instance"
# A fullscreen app must stay in front this long before a screen goes idle, so
# passing windows (Alt+Tab, a screenshot overlay) never make widgets blink.
FULLSCREEN_DELAY = 1.2

# Which providers each widget type reads.
NEEDS = {
    "media": {"media"},
    "system": {"system"},
    "weather": {"weather"},
    "profile": {"system", "weather", "github"},
    "github": {"github"},
    "picture": set(),
    "clock": set(),
    "time": set(),
    "calendar": set(),
    "network": {"network"},
    "storage": {"storage"},
    "clipboard": {"clipboard"},
    "notifications": {"notifications"},
    "xd": {"xd"},
    "mixer": {"audio"},
    "notes": set(),
    "timer": set(),
    "launcher": set(),
    "games": {"games"},
    "league": {"league"},
    "countdown": set(),
    "slideshow": set(),
    "quote": set(),
    "dev": {"devdash"},
    "devices": {"devices"},
}
# Polling providers that pause while every screen is covered by a fullscreen app.
PAUSABLE = ("system", "weather", "github", "network", "storage", "notifications", "audio", "games", "league", "devdash", "devices")


class Desk(QObject):
    """Exposed to QML as `Desk`."""

    widgetsChanged = Signal()
    editingChanged = Signal()
    suspendedChanged = Signal()
    wallpaperChanged = Signal()
    errorChanged = Signal()
    selectedChanged = Signal()
    screensChanged = Signal()
    lockShotChanged = Signal()

    def __init__(self, app: QApplication, store: ConfigStore, theme: Theme, displays: Displays, providers: dict[str, QObject]):
        super().__init__()
        self._app = app
        self._store = store
        self._theme = theme
        self._displays = displays
        self._providers = providers
        self._editing = False
        self._lock_shot = False
        self._suspended = False
        self._selected = ""
        self._needed: set[str] = set()
        self._fullscreen_since: dict[str, float] = {}
        self._wallpaper_url = ""
        self._wallpaper_mtime = 0.0
        self.dock_provider = None
        self.notify_hook = None  # (title, text) -> tray message, set once the tray exists

        store.changed.connect(self._apply_config)
        providers["media"].artChanged.connect(theme.set_art)
        displays.screensChanged.connect(self._on_screens)
        self._apply_config(initial=True)

        self._wall_timer = QTimer(self, interval=5000, timeout=self._check_wallpaper)
        self._wall_timer.start()
        self._check_wallpaper()

        self._recheck = QTimer(self, singleShot=True, interval=120, timeout=self._check_fullscreen)
        self._fullscreen_timer = QTimer(self, interval=1000, timeout=self._check_fullscreen)
        self._fullscreen_timer.start()
        # Also look again the moment focus moves, so widgets come back straight away.
        self._window_events = None if SNAPSHOT else desktop.WindowEvents(lambda: self._recheck.start(120))

    # ---- config ----------------------------------------------------------------

    def _apply_config(self, initial: bool = False):
        cfg = self._store.config
        self._theme.configure(cfg.get("theme", {}), cfg.get("style", {}))
        settings = cfg.get("settings", {})
        self._providers["weather"].configure(settings.get("weather", {}))
        git = settings.get("git") if isinstance(settings.get("git"), dict) else {}
        self._providers["github"].configure({
            "source": git.get("source") or "github",
            "profile": git.get("profile") or "github",
            "github_user": git.get("github_user", settings.get("github_user", "")),
            "github_token": git.get("github_token", settings.get("github_token", "")),
            "gitea_url": git.get("gitea_url", ""),
            "gitea_token": git.get("gitea_token", ""),
        })
        widgets = cfg["widgets"]
        for w in widgets:
            if w["type"] == "github":
                self._providers["github"].weeks = int(w["options"].get("weeks", 24))
        devdash = self._providers["devdash"]
        devdash.repos = [str(r).strip() for w in widgets if w["type"] == "dev"
                         for r in str(w["options"].get("ci_repos", "")).replace(",", "\n").splitlines() if str(r).strip()]
        devdash.configure({
            "source": git.get("source") or "github",
            "github_user": git.get("github_user", ""), "github_token": git.get("github_token", ""),
            "gitea_url": git.get("gitea_url", ""), "gitea_token": git.get("gitea_token", ""),
        })
        self._providers["clipboard"].keep_images = any(
            w["type"] == "clipboard" and w["options"].get("images", True) is not False for w in widgets)

        needed = set()
        for w in widgets:
            needs = set(NEEDS.get(w["type"], set()))
            if w["type"] == "profile" and str(w["options"].get("avatar", "github")) != "github":
                needs.discard("github")
            if w["type"] == "media" and w["options"].get("lyrics", True):
                self._providers["media"].want_lyrics = True
            needed |= needs
        self._needed = needed
        self._run_providers()
        if not initial:
            self.widgetsChanged.emit()
            self.errorChanged.emit()

    def _run_providers(self):
        for name, provider in self._providers.items():
            if name in self._needed and not (self._suspended and name in PAUSABLE):
                provider.start()
            elif name != "media" and (name not in self._needed or name in PAUSABLE):
                provider.stop()

    def _on_screens(self):
        self.screensChanged.emit()
        self.widgetsChanged.emit()  # widgets of an unplugged screen move to the main one

    # ---- QML: data -------------------------------------------------------------

    @Property("QVariantList", notify=widgetsChanged)
    def widgets(self):
        """The config's widgets, each with `display`: the screen it shows on right now."""
        return [{**w, "display": self._displays.slot_number(w.get("screen", 1))} for w in self._store.config["widgets"]]

    @Property("QVariantMap", notify=widgetsChanged)
    def config(self):
        cfg = self._store.config
        return {k: cfg.get(k, {}) for k in ("theme", "style", "settings", "dock", "search")}

    @Slot(str, "QVariant")
    def setSetting(self, path: str, value):
        if isinstance(value, float) and value.is_integer() and not path.startswith(("style.", "dock.zoom")):
            value = int(value)
        self._store.set_setting(path, value)

    @Property(int, notify=widgetsChanged)
    def grid(self):
        return int(self._store.config.get("settings", {}).get("grid", 10))

    @Property(str, notify=errorChanged)
    def error(self):
        return self._store.error or ""

    @Property("QVariantMap", notify=widgetsChanged)
    def dock(self):
        return self._store.config.get("dock") or {}

    @Property(int, notify=screensChanged)
    def screenCount(self):
        return len(self._displays.slots)

    @Property(bool, notify=editingChanged)
    def editing(self):
        return self._editing

    @Property(bool, notify=lockShotChanged)
    def lockShot(self):
        """True only while the lock screen picture is being painted.

        Windows draws its own clock and date on the lock screen, so ours would
        sit beside it showing the time the picture was taken. Widgets whose type
        is listed under lock_screen.hide leave the picture while this is on, and
        come straight back: it is one frame, and nothing about the desk changes.
        """
        return self._lock_shot

    def set_lock_shot(self, on: bool):
        if on != self._lock_shot:
            self._lock_shot = on
            self.lockShotChanged.emit()

    @Property("QVariantList", notify=lockShotChanged)
    def lockHidden(self):
        """Widget types kept out of the lock screen picture."""
        section = self._store.config.get("lock_screen") or {}
        hide = section.get("hide")
        return [str(t) for t in hide] if isinstance(hide, list) else ["clock", "time"]

    @Property(bool, notify=suspendedChanged)
    def suspended(self):
        """Every screen is covered by a fullscreen app."""
        return self._suspended

    @Property(str, notify=wallpaperChanged)
    def wallpaper(self):
        return self._wallpaper_url

    @Property(str, notify=selectedChanged)
    def selected(self):
        """The widget whose options are open (one across all screens)."""
        return self._selected

    # ---- QML: actions ----------------------------------------------------------

    @Slot(QObject)
    def registerWindow(self, window):
        """A desk window was created or shown again: pin it to the desktop layer."""
        hwnd = int(window.winId())
        desktop.pin_to_desktop(hwnd)
        desktop.set_activatable(hwnd, self._editing)
        desktop.bring_to_front(hwnd) if self._editing else desktop.send_to_back(hwnd)

    @Slot(QObject, "QVariantList")
    def setMask(self, window, rects):
        """Clip a window to what it shows: drawing and clicks outside fall through to what's below."""
        region = QRegion()
        for x, y, w, h in rects:
            region = region.united(QRegion(int(x), int(y), max(1, int(w)), max(1, int(h))))
        window.setMask(region)

    @Slot("QVariantMap", result="QVariantMap")
    def placeWidget(self, drop):
        """Save where a widget was dropped or resized.

        drop: id, display (the screen it shows on), screen (the one its config
        names; they differ while that screen is unplugged), left / top (in the
        display's area), width / height, scale; optionally anchor (else the
        nearest one), and cursorX / cursorY / grabX / grabY (global cursor, and
        where the widget was grabbed) to move it to the screen the cursor was
        released on.
        Returns what was saved: screen, display, anchor, x, y, scale."""
        slots = self._displays.slots
        number = self._displays.slot_number(int(drop.get("display") or 1))
        slot = slots[number - 1] if slots else None
        left, top = float(drop.get("left", 0)), float(drop.get("top", 0))
        width, height = float(drop.get("width", 0)), float(drop.get("height", 0))
        moved = False
        if slot is not None and "cursorX" in drop:
            target = self._displays.slot_at(drop["cursorX"], drop["cursorY"])
            if target is not None and target is not slot:
                area = target.area
                left = float(drop["cursorX"]) - area.x() - float(drop.get("grabX", 0))
                top = float(drop["cursorY"]) - area.y() - float(drop.get("grabY", 0))
                slot, number, moved = target, target.number, True
        area_w = slot.area.width() if slot is not None else width
        area_h = slot.area.height() if slot is not None else height
        left = max(0.0, min(area_w - width, left))
        top = max(0.0, min(area_h - height, top))
        anchor = layout.normalize(drop["anchor"]) if drop.get("anchor") else layout.nearest(left, top, width, height, area_w, area_h)
        x, y = layout.offsets(anchor, left, top, width, height, area_w, area_h)
        scale = round(float(drop.get("scale") or 1), 2)
        # A widget standing in on the main display for an unplugged screen goes
        # back there when it returns, unless it was dragged onto another screen.
        configured = int(drop.get("screen") or number)
        screen = number if moved or self._displays.slot_number(configured) == configured else configured
        self._store.place_widget(str(drop.get("id", "")), x, y, scale, screen=screen, anchor=anchor)
        return {"screen": screen, "display": number, "anchor": anchor, "x": x, "y": y, "scale": scale}

    @Slot(float, float, result=int)
    def screenAt(self, x: float, y: float) -> int:
        """Screen number under a global point, 0 if none."""
        slot = self._displays.slot_at(x, y)
        return slot.number if slot is not None else 0

    @Slot(str, str, "QVariant")
    def setOption(self, widget_id: str, key: str, value):
        if isinstance(value, float) and value.is_integer() and key != "scale":
            value = int(value)
        self._store.set_option(widget_id, key, value)

    @Slot(str, int, result=str)
    def addWidget(self, widget_type: str, screen: int) -> str:
        """New widgets start in the middle of the screen they were added on."""
        return self._store.add_widget(widget_type, 0, 0, screen=screen, anchor="center")

    @Slot(str)
    def removeWidget(self, widget_id: str):
        if widget_id == self._selected:
            self.select("")
        self._store.remove_widget(widget_id)

    @Slot(str)
    def select(self, widget_id: str):
        if widget_id != self._selected:
            self._selected = widget_id
            self.selectedChanged.emit()

    @Slot(bool)
    def setEditing(self, on: bool):
        if on == self._editing:
            return
        self._editing = on
        if on:
            # Nothing stays hidden while arranging.
            self._fullscreen_since.clear()
            self._set_fullscreen(set())
        else:
            self.select("")
        for window in self._displays.desk_windows():
            hwnd = int(window.winId())
            # Editing needs the keyboard (text options), so allow focus then.
            desktop.set_activatable(hwnd, on)
            desktop.bring_to_front(hwnd) if on else desktop.send_to_back(hwnd)
        self.editingChanged.emit()
        tray_refresh()

    @Slot(str, result="QVariantList")
    def listImages(self, folder: str):
        """Image files in a folder (for the slideshow), as file URLs."""
        p = Path(os.path.expandvars(os.path.expanduser(str(folder))))
        if not p.is_dir():
            return []
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
        return [QUrl.fromLocalFile(str(f)).toString() for f in sorted(p.iterdir()) if f.suffix.lower() in exts][:500]

    @Slot(str)
    def launch(self, target: str):
        """Open an app (path or AppUserModelId), file, folder, URL or settings page."""
        target = os.path.expandvars(os.path.expanduser(str(target).strip()))
        if not target:
            return
        if "!" in target and "\\" not in target and "://" not in target:
            target = f"shell:AppsFolder\\{target}"
        try:
            os.startfile(target)
        except OSError as e:
            print(f"[unidesk] could not open {target}: {e}")

    @Slot(str, result=str)
    def iconFor(self, target: str) -> str:
        """Shell icon for a launcher entry."""
        from .dock import winapi

        target = os.path.expandvars(os.path.expanduser(str(target).strip()))
        if "://" in target and not target.startswith("file:"):
            return ""
        source = f"shell:AppsFolder\\{target}" if "!" in target and "\\" not in target else target
        try:
            winapi.com_init()
            path = winapi.icon_png(source, 96, Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk" / "icons")
        except Exception:
            path = ""
        return QUrl.fromLocalFile(path).toString() if path else ""

    @Slot(str, str)
    def notify(self, title: str, text: str):
        if self.notify_hook:
            self.notify_hook(title, text)

    @Slot(QObject, bool)
    def focusInput(self, window, on: bool):
        """Let a desk window take the keyboard while one of its text boxes (notes) is in use."""
        if window is None:
            return
        hwnd = int(window.winId())
        desktop.set_activatable(hwnd, on or self._editing)
        if on:
            from .dock import winapi

            winapi.activate(hwnd)
            window.requestActivate()

    @Slot(str, result=str)
    def fileUrl(self, path: str) -> str:
        p = Path(os.path.expandvars(os.path.expanduser(str(path))))
        return QUrl.fromLocalFile(str(p)).toString() if p.exists() else ""

    @Slot(str)
    def openUrl(self, url: str):
        if url.startswith(("https://", "http://")):
            os.startfile(url)

    @Slot(str)
    def systemAction(self, action: str):
        commands = {
            "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "restart": ["shutdown", "/r", "/t", "0"],
            "shutdown": ["shutdown", "/s", "/t", "0"],
            "signout": ["shutdown", "/l"],
        }
        if action == "settings":
            os.startfile("ms-settings:")
        elif action in commands:
            subprocess.Popen(commands[action], creationflags=0x08000000)

    # ---- background checks -----------------------------------------------------

    def _check_wallpaper(self):
        try:
            mtime = WALLPAPER.stat().st_mtime
        except OSError:
            return
        if mtime == self._wallpaper_mtime:
            return
        self._wallpaper_mtime = mtime
        self._wallpaper_url = QUrl.fromLocalFile(str(WALLPAPER)).toString() + f"?v={int(mtime)}"
        self._theme.set_wallpaper(str(WALLPAPER))
        self.wallpaperChanged.emit()

    def _check_fullscreen(self):
        """Idle each screen (hide its widgets and dock, pause polling) while a game
        or video is fullscreen on it; and keep the desk windows on the desktop layer."""
        if self._editing or SNAPSHOT:
            return
        for window in self._displays.desk_windows():
            if window.isVisible():
                hwnd = int(window.winId())
                if not desktop.pinned(hwnd):
                    desktop.pin_to_desktop(hwnd)
                    desktop.send_to_back(hwnd)
        try:
            covered = desktop.fullscreen_monitors(os.getpid())
        except Exception as e:  # never let a failed look hide the desk
            print(f"[unidesk] fullscreen check failed: {e}")
            covered = set()
        now = time.monotonic()
        self._fullscreen_since = {name: self._fullscreen_since.get(name, now) for name in covered}
        confirmed = {name for name, since in self._fullscreen_since.items() if now - since >= FULLSCREEN_DELAY}
        waiting = [since + FULLSCREEN_DELAY - now for name, since in self._fullscreen_since.items() if name not in confirmed]
        if waiting:
            self._recheck.start(max(50, int(min(waiting) * 1000) + 30))
        self._set_fullscreen(confirmed)

    def _set_fullscreen(self, devices: set[str]):
        self._displays.set_suspended(devices)
        slots = self._displays.slots
        idle = bool(slots) and all(slot.suspended for slot in slots)
        if idle == self._suspended:
            return
        self._suspended = idle
        if self.dock_provider is not None:
            self.dock_provider.suspended = idle
        self._run_providers()
        self.suspendedChanged.emit()


# ---- tray ------------------------------------------------------------------------

_tray_refresh = None


def tray_refresh():
    if _tray_refresh:
        _tray_refresh()


def _tray_icon(color: str) -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    for x, y in ((2, 2), (17, 2), (2, 17), (17, 17)):
        p.drawRoundedRect(x, y, 13, 13, 4, 4)
    p.end()
    return QIcon(pix)


def _startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, "unidesk")
            return True
    except OSError:
        return False


def _set_startup(on: bool):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}"'
            else:
                pythonw = Path(sys.executable).with_name("pythonw.exe")
                command = f'"{pythonw}" "{HERE.parent / "unidesk.pyw"}"'
            winreg.SetValueEx(key, "unidesk", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "unidesk")
            except OSError:
                pass


def main():
    global _tray_refresh

    if not os.environ.get("QSG_RHI_BACKEND"):
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("unidesk")

    # One copy at a time; a second launch just toggles edit mode in the first.
    # `--quit` instead closes the running copy properly (taskbar, reserved
    # space and other windows' frames put back) and waits for it to finish.
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE)
    if probe.waitForConnected(300):
        if "--quit" in sys.argv:
            probe.write(b"quit")
            probe.waitForBytesWritten(1000)
            if probe.waitForReadyRead(3000):  # it answers with its process id
                try:
                    psutil.Process(int(bytes(probe.readAll()).strip() or 0)).wait(timeout=15)
                except (ValueError, psutil.Error):
                    pass
            return 0
        probe.write(b"edit")
        probe.waitForBytesWritten(300)
        return 0
    if "--quit" in sys.argv:
        return 0
    QLocalServer.removeServer(INSTANCE)
    server = QLocalServer()
    server.listen(INSTANCE)

    fonts = HERE / "fonts"
    family = "Segoe UI Variable Display"
    fid = QFontDatabase.addApplicationFont(str(fonts / "GoogleSansFlex-unidesk.ttf"))
    if fid >= 0:
        family = QFontDatabase.applicationFontFamilies(fid)[0]
    icon_family = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(fonts / "MaterialSymbolsRounded-subset.ttf")))[0]

    store = ConfigStore()
    theme = Theme(family, icon_family)
    providers = {
        "media": Media(), "system": System(), "weather": Weather(), "github": GitHub(),
        "network": Network(), "storage": Storage(), "clipboard": Clipboard(), "notifications": Notifications(),
        "audio": Audio(), "games": Games(), "league": League(), "devdash": DevDash(), "devices": Devices(),
        "xd": XD(),
    }
    notes = Notes()
    media = providers["media"]
    displays = Displays(app)
    desk = Desk(app, store, theme, displays, providers)
    frames = WindowFrames(store, theme)
    app_themes = AppThemes(store, theme)
    caption = CaptionButtons(store, theme)
    lock_screen = LockScreen(store, displays, WALLPAPER, desk)
    account_picture = AccountPicture(store, theme, WALLPAPER)

    dock = Dock(store)
    desk.dock_provider = dock
    dock_settings = lambda: store.config.get("dock") or {}

    def start_dock():
        if dock_settings().get("enabled", True) is not False and not dock.running:
            media.start()
            dock.start(passive=bool(SNAPSHOT))

    start_dock()
    displays.want_dock = lambda slot: dock_settings().get("enabled", True) is not False and (
        slot.number == 1 or dock_settings().get("all_screens", True) is not False)
    displays.before_close = dock.forget_window

    engine = QQmlApplicationEngine()
    engine.addImageProvider("clipboard", ClipboardImages(providers["clipboard"]))
    ctx = engine.rootContext()
    search = Search(store)
    updater = Updater()
    for name, obj in (("Desk", desk), ("Theme", theme), ("Media", media), ("System", providers["system"]),
                      ("Weather", providers["weather"]), ("GitHub", providers["github"]), ("Network", providers["network"]),
                      ("Storage", providers["storage"]), ("Clipboard", providers["clipboard"]),
                      ("Notifications", providers["notifications"]), ("Dock", dock), ("Search", search), ("Updater", updater),
                      ("Audio", providers["audio"]), ("Games", providers["games"]), ("League", providers["league"]),
                      ("DevDash", providers["devdash"]), ("Devices", providers["devices"]), ("Notes", notes),
                      ("XD", providers["xd"])):
        ctx.setContextProperty(name, obj)
    if not displays.attach(engine):
        return 1

    def on_config():
        start_dock()
        displays.sync_windows()  # dock turned on or off, or on every screen or just the main one

    store.changed.connect(on_config)
    # Search opens on the dock of the screen you're looking at.
    search.screen_at_cursor = lambda: next((s.number for s in [displays.slot_at_cursor()] if s is not None and s.dock_window is not None), 1)
    # Put the real taskbar and other apps' window frames back however we exit.
    app.aboutToQuit.connect(dock.stop)
    app.aboutToQuit.connect(frames.restore)
    if not SNAPSHOT:
        frames.configure()
        app_themes.configure()

    # tray
    tray = QSystemTrayIcon(_tray_icon(theme.c.get("primary", "#ffb1c1")))
    tray.setToolTip("unidesk")
    menu = QMenu()
    edit_action = QAction("Edit widgets\tCtrl+Alt+E")
    edit_action.triggered.connect(lambda: desk.setEditing(not desk.editing))
    folder_action = QAction("Open config folder")
    folder_action.triggered.connect(lambda: os.startfile(CONFIG_DIR))
    file_action = QAction("Edit config.yaml")
    file_action.triggered.connect(lambda: sharing.open_text_file(CONFIG_FILE))

    def export_clicked():
        from PySide6.QtWidgets import QFileDialog

        default = str(Path.home() / "Desktop" / "unidesk-settings.yaml")
        path, _ = QFileDialog.getSaveFileName(None, "Export unidesk settings", default, "unidesk settings (*.yaml)")
        if not path:
            return
        try:
            removed = sharing.export_settings(Path(path))
        except Exception as e:
            tray.showMessage("unidesk", f"Export failed: {e}")
            return
        note = "Left out: " + ", ".join(removed) if removed else "Nothing personal to remove."
        tray.showMessage("Settings exported", f"{Path(path).name} is ready to share. {note}")

    def import_clicked():
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(None, "Import unidesk settings", str(Path.home() / "Downloads"), "unidesk settings (*.yaml *.yml)")
        if not path:
            return
        try:
            sharing.import_settings(Path(path))
        except Exception as e:
            tray.showMessage("unidesk", f"Import failed: {e}")
            return
        tray.showMessage("Settings imported", "Your accounts and dock pins were kept. The old setup was saved as config.before-import.yaml.")

    update_action = QAction("Check for updates")

    def update_clicked():
        if updater.state in ("available", "error"):
            updater.install()
        else:
            updater.check()
            tray.showMessage("unidesk", f"Checking for updates (you have {updater.current})…")

    update_action.triggered.connect(update_clicked)

    def refresh_update_action():
        labels = {
            "available": f"Install update {updater.version}",
            "downloading": f"Downloading update… {int(updater.progress * 100)}%",
            "installing": "Installing update…",
            "error": f"Update failed - try again",
        }
        update_action.setText(labels.get(updater.state, f"Check for updates (v{updater.current})"))

    updater.changed.connect(refresh_update_action)
    refresh_update_action()

    export_action = QAction("Export settings to share…")
    export_action.triggered.connect(export_clicked)
    import_action = QAction("Import settings…")
    import_action.triggered.connect(import_clicked)
    pins_action = QAction("Re-import taskbar pins into the dock")
    pins_action.triggered.connect(dock.importTaskbarPins)
    startup_action = QAction("Start with Windows", checkable=True, checked=_startup_enabled())
    startup_action.toggled.connect(_set_startup)
    quit_action = QAction("Quit")
    quit_action.triggered.connect(app.quit)
    for action in (edit_action, None, file_action, folder_action, export_action, import_action, pins_action, startup_action, None, update_action, quit_action):
        menu.addSeparator() if action is None else menu.addAction(action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: reason == QSystemTrayIcon.ActivationReason.DoubleClick and desk.setEditing(not desk.editing))
    tray.show()

    def refresh():
        edit_action.setText("Done editing\tCtrl+Alt+E" if desk.editing else "Edit widgets\tCtrl+Alt+E")

    _tray_refresh = refresh
    theme.colorsChanged.connect(lambda: tray.setIcon(_tray_icon(theme.c.get("primary", "#ffb1c1"))))

    def on_connection():
        sock = server.nextPendingConnection()

        def read():
            if bytes(sock.readAll()).strip() == b"quit":
                sock.write(str(os.getpid()).encode())  # `--quit` waits for this process to end
                sock.flush()
                QTimer.singleShot(0, app.quit)
            else:
                desk.setEditing(not desk.editing)

        sock.readyRead.connect(read)

    server.newConnection.connect(on_connection)

    hotkey = GlobalHotkey()
    hotkey.add("ctrl+alt+e", lambda: desk.setEditing(not desk.editing))
    search_cfg = store.config.get("search") or {}
    if dock_settings().get("enabled", True) is not False and search_cfg.get("enabled", True) and search_cfg.get("hotkey"):
        hotkey.add(str(search_cfg["hotkey"]), search.toggle)
    app.installNativeEventFilter(hotkey)

    updater.notify = lambda title, text: tray.showMessage(title, text)
    desk.notify_hook = lambda title, text: tray.showMessage(title, text)
    if not SNAPSHOT:
        updater.start()

    if SNAPSHOT:
        tray.hide()
        if os.environ.get("UNIDESK_SNAPSHOT_EDIT"):
            QTimer.singleShot(2000, lambda: desk.setEditing(True))
            # UNIDESK_SNAPSHOT_SELECT=<widget id>: with its options open
            QTimer.singleShot(2500, lambda: desk.select(os.environ.get("UNIDESK_SNAPSHOT_SELECT", "")))
        delay = int(os.environ.get("UNIDESK_SNAPSHOT_DELAY", "9000"))
        QTimer.singleShot(delay, lambda: (snapshot(displays, SNAPSHOT), app.quit()))

    code = app.exec()
    media.stop()
    # Everything that matters was put back on aboutToQuit (taskbars, reserved space,
    # other windows' frames). Leave now: tearing down windows, QML and providers in
    # Python's order only fills the log with errors, or crashes if forced.
    tray.hide()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def snapshot(displays: Displays, out: str):
    """Paint every screen's wallpaper, desk and dock at their real positions."""
    slots = displays.slots
    bounds = QRect()
    for slot in slots:
        bounds = bounds.united(slot.rect)
    canvas = QImage(bounds.width(), bounds.height(), QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("#101014"))
    painter = QPainter(canvas)
    wall = QImage(str(WALLPAPER))
    for slot in slots:
        rect, origin = slot.rect, bounds.topLeft()
        if not wall.isNull():
            scaled = wall.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            crop = QRect((scaled.width() - rect.width()) // 2, (scaled.height() - rect.height()) // 2, rect.width(), rect.height())
            painter.drawImage(rect.topLeft() - origin, scaled, crop)
        if slot.desk_window is not None:
            painter.drawImage(slot.area.topLeft() - origin, slot.desk_window.grabWindow())
        if slot.dock_window is not None:
            painter.drawImage(QPoint(slot.dock_window.x(), slot.dock_window.y()) - origin, slot.dock_window.grabWindow())
    painter.end()
    canvas.save(out)
    print(f"[unidesk] snapshot: {len(slots)} screens -> {out}")


# ---- Ctrl+Alt+E ------------------------------------------------------------------


class GlobalHotkey(QAbstractNativeEventFilter):
    """System-wide shortcuts like "ctrl+alt+e" or "alt+space"."""

    WM_HOTKEY = 0x0312
    MODS = {"ctrl": 0x2, "control": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8}
    KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "`": 0xC0}

    def __init__(self):
        super().__init__()
        self._actions: dict[int, object] = {}

    def add(self, combo: str, callback) -> bool:
        mods, key = 0x4000, 0  # MOD_NOREPEAT
        for part in combo.lower().replace(" ", "").split("+"):
            if part in self.MODS:
                mods |= self.MODS[part]
            elif part in self.KEYS:
                key = self.KEYS[part]
            elif len(part) == 1:
                key = ord(part.upper())
            elif part.startswith("f") and part[1:].isdigit():
                key = 0x6F + int(part[1:])
        if not key:
            return False
        hotkey_id = 0xE000 + len(self._actions)
        if not ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mods, key):
            print(f"[unidesk] hotkey {combo} is taken by another app")
            return False
        self._actions[hotkey_id] = callback
        return True

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY and msg.wParam in self._actions:
                self._actions[msg.wParam]()
                return True, 0
        return False, 0
