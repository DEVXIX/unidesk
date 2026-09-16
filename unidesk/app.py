"""unidesk: YASB-style desktop widgets in Qt Quick.

One transparent window over the screen, clipped to the widgets and pinned
to the desktop layer.
Everything visual lives in qml/; this file wires config, theme and data
providers together and owns the tray, edit mode and idle-while-gaming."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, Property, QObject, QRect, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFontDatabase, QIcon, QPainter, QPixmap, QRegion
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import desktop, sharing
from .config import CONFIG_DIR, CONFIG_FILE, ConfigStore
from .dock.provider import Dock
from .search import Search
from .updater import Updater
from .providers.github import GitHub
from .providers.media import Media
from .providers.system import System
from .providers.weather import Weather
from .theme import Theme

HERE = Path(__file__).resolve().parent
WALLPAPER = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# UNIDESK_SNAPSHOT=out.png: render off-screen, save a composite picture, quit.
SNAPSHOT = os.environ.get("UNIDESK_SNAPSHOT", "")
INSTANCE = "unidesk-snapshot" if SNAPSHOT else "unidesk-single-instance"

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
}


class Desk(QObject):
    """Exposed to QML as `Desk`."""

    widgetsChanged = Signal()
    editingChanged = Signal()
    suspendedChanged = Signal()
    wallpaperChanged = Signal()
    errorChanged = Signal()
    areaChanged = Signal()

    def __init__(self, app: QApplication, store: ConfigStore, theme: Theme, media: Media, system: System, weather: Weather, github: GitHub):
        super().__init__()
        self._app = app
        self._store = store
        self._theme = theme
        self._media, self._system, self._weather, self._github = media, system, weather, github
        self._editing = False
        self._suspended = False
        self._window: QQuickWindow | None = None
        self._wallpaper_url = ""
        self._wallpaper_mtime = 0.0

        store.changed.connect(self._apply_config)
        media.artChanged.connect(theme.set_art)
        self._apply_config(initial=True)

        self._wall_timer = QTimer(self, interval=5000, timeout=self._check_wallpaper)
        self._wall_timer.start()
        self._check_wallpaper()

        self._fullscreen_timer = QTimer(self, interval=1500, timeout=self._check_fullscreen)
        self._fullscreen_timer.start()

        screen = app.primaryScreen()
        screen.availableGeometryChanged.connect(lambda _: self.areaChanged.emit())
        screen.geometryChanged.connect(lambda _: self.areaChanged.emit())

    # ---- config ----------------------------------------------------------------

    def _apply_config(self, initial: bool = False):
        cfg = self._store.config
        self._theme.configure(cfg.get("theme", {}), cfg.get("style", {}))
        settings = cfg.get("settings", {})
        self._weather.configure(settings.get("weather", {}))
        git = settings.get("git") if isinstance(settings.get("git"), dict) else {}
        self._github.configure({
            "source": git.get("source") or "github",
            "profile": git.get("profile") or "github",
            "github_user": git.get("github_user", settings.get("github_user", "")),
            "github_token": git.get("github_token", settings.get("github_token", "")),
            "gitea_url": git.get("gitea_url", ""),
            "gitea_token": git.get("gitea_token", ""),
        })
        for w in cfg["widgets"]:
            if w["type"] == "github":
                self._github.weeks = int(w["options"].get("weeks", 24))

        needed = set()
        for w in cfg["widgets"]:
            needs = set(NEEDS.get(w["type"], set()))
            if w["type"] == "profile" and str(w["options"].get("avatar", "github")) != "github":
                needs.discard("github")
            if w["type"] == "media" and w["options"].get("lyrics", True):
                self._media.want_lyrics = True
            needed |= needs
        for name, provider in (("media", self._media), ("system", self._system), ("weather", self._weather), ("github", self._github)):
            if name in needed and not self._suspended:
                provider.start()
            elif name not in needed and name != "media":
                provider.stop()
        self._needed = needed
        if not initial:
            self.widgetsChanged.emit()
            self.errorChanged.emit()

    # ---- QML: data -------------------------------------------------------------

    @Property("QVariantList", notify=widgetsChanged)
    def widgets(self):
        return self._store.config["widgets"]

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

    @Property(QRect, notify=areaChanged)
    def area(self):
        area = self._app.primaryScreen().availableGeometry()
        if SNAPSHOT:
            area.translate(-20000, 0)  # render far off-screen; see snapshot()
        return area

    @Property(QRect, notify=areaChanged)
    def screenRect(self):
        rect = self._app.primaryScreen().geometry()
        if SNAPSHOT:
            rect.translate(-20000, 0)
        return rect

    @Property("QVariantMap", notify=widgetsChanged)
    def dock(self):
        return self._store.config.get("dock") or {}

    @Property(bool, notify=editingChanged)
    def editing(self):
        return self._editing

    @Property(bool, notify=suspendedChanged)
    def suspended(self):
        return self._suspended

    @Property(str, notify=wallpaperChanged)
    def wallpaper(self):
        return self._wallpaper_url

    # ---- QML: actions ----------------------------------------------------------

    @Slot(QObject)
    def registerWindow(self, window):
        first = self._window is None
        self._window = window
        hwnd = int(window.winId())
        if first:
            desktop.pin_to_desktop(hwnd)
        if self._editing:
            desktop.bring_to_front(hwnd)
        else:
            desktop.send_to_back(hwnd)

    @Slot(QObject, "QVariantList")
    def setMask(self, window, rects):
        """Clip the desk window to the widgets: drawing and clicks outside fall through to the desktop."""
        region = QRegion()
        for x, y, w, h in rects:
            region = region.united(QRegion(int(x), int(y), max(1, int(w)), max(1, int(h))))
        window.setMask(region)

    @Slot(str, int, int, float)
    def placeWidget(self, widget_id: str, x: int, y: int, scale: float):
        self._store.place_widget(widget_id, x, y, scale)

    @Slot(str, str, "QVariant")
    def setOption(self, widget_id: str, key: str, value):
        if isinstance(value, float) and value.is_integer() and key != "scale":
            value = int(value)
        self._store.set_option(widget_id, key, value)

    @Slot(str, int, int, result=str)
    def addWidget(self, widget_type: str, x: int, y: int) -> str:
        return self._store.add_widget(widget_type, x, y)

    @Slot(str)
    def removeWidget(self, widget_id: str):
        self._store.remove_widget(widget_id)

    @Slot(bool)
    def setEditing(self, on: bool):
        if on == self._editing:
            return
        self._editing = on
        if self._window is not None:
            hwnd = int(self._window.winId())
            # Editing needs the keyboard (text options), so allow focus then.
            desktop.set_activatable(hwnd, on)
            desktop.bring_to_front(hwnd) if on else desktop.send_to_back(hwnd)
        self.editingChanged.emit()
        tray_refresh()

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
        """Hide everything (so nothing renders or polls) while a game or video is fullscreen."""
        if self._editing or SNAPSHOT:
            return
        busy = desktop.fullscreen_app_active(os.getpid())
        if busy == self._suspended:
            return
        self._suspended = busy
        if getattr(self, "dock_provider", None) is not None:
            self.dock_provider.suspended = busy
        self._fullscreen_timer.setInterval(3000 if busy else 1500)
        for name, provider in (("system", self._system), ("weather", self._weather), ("github", self._github)):
            if busy:
                provider.stop()
            elif name in self._needed:
                provider.start()
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
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE)
    if probe.waitForConnected(300):
        probe.write(b"edit")
        probe.waitForBytesWritten(300)
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
    media, system, weather, github = Media(), System(), Weather(), GitHub()
    desk = Desk(app, store, theme, media, system, weather, github)

    dock = Dock(store)
    desk.dock_provider = dock
    dock_on = bool((store.config.get("dock") or {}).get("enabled", True))
    if dock_on:
        media.start()
        dock.start(passive=bool(SNAPSHOT))

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    search = Search(store)
    updater = Updater()
    for name, obj in (("Desk", desk), ("Theme", theme), ("Media", media), ("System", system), ("Weather", weather), ("GitHub", github), ("Dock", dock), ("Search", search), ("Updater", updater)):
        ctx.setContextProperty(name, obj)
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    if dock_on:
        engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "DockBar.qml")))
        desk._dock_window = engine.rootObjects()[-1]
    # Put the real taskbar back however we exit.
    app.aboutToQuit.connect(dock.stop)

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
        sock.readyRead.connect(lambda: desk.setEditing(not desk.editing))

    server.newConnection.connect(on_connection)

    hotkey = GlobalHotkey()
    hotkey.add("ctrl+alt+e", lambda: desk.setEditing(not desk.editing))
    search_cfg = store.config.get("search") or {}
    if dock_on and search_cfg.get("enabled", True) and search_cfg.get("hotkey"):
        hotkey.add(str(search_cfg["hotkey"]), search.toggle)
    app.installNativeEventFilter(hotkey)

    updater.notify = lambda title, text: tray.showMessage(title, text)
    if not SNAPSHOT:
        updater.start()

    if SNAPSHOT:
        tray.hide()
        if os.environ.get("UNIDESK_SNAPSHOT_EDIT"):
            QTimer.singleShot(2000, lambda: desk.setEditing(True))
        delay = int(os.environ.get("UNIDESK_SNAPSHOT_DELAY", "9000"))
        QTimer.singleShot(delay, lambda: (snapshot(app, desk, SNAPSHOT), app.quit()))

    code = app.exec()
    media.stop()
    return code


def snapshot(app: QApplication, desk: Desk, out: str):
    """Paint every widget window onto the wallpaper at its real position."""
    from PySide6.QtGui import QImage

    area = app.primaryScreen().availableGeometry()
    canvas = QImage(area.width(), area.height(), QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("#101014"))
    painter = QPainter(canvas)
    wall = QImage(str(WALLPAPER))
    if not wall.isNull():
        painter.drawImage(canvas.rect(), wall.scaled(canvas.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
    if desk._window is not None:
        painter.drawImage(0, 0, desk._window.grabWindow())
    dock_window = getattr(desk, "_dock_window", None)
    if dock_window is not None:
        painter.end()
        full = app.primaryScreen().geometry()
        framed = QImage(full.width(), full.height(), QImage.Format.Format_ARGB32_Premultiplied)
        framed.fill(QColor("#101014"))
        painter = QPainter(framed)
        painter.drawImage(area.x() - full.x(), area.y() - full.y(), canvas)
        painter.drawImage(0, dock_window.y() - (full.y()), dock_window.grabWindow())
        canvas = framed
    painter.end()
    canvas.save(out)
    print(f"[unidesk] snapshot: {len(desk._store.config['widgets'])} widgets -> {out}")


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
