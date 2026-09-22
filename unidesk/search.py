"""unidesk search: apps (everything in the Start menu, Store apps included),
a calculator, Windows settings pages, and hand-offs to file and web search.

The app list comes from `Get-StartApps` (one short PowerShell run, refreshed
at most every 15 minutes). Icons are rendered lazily for visible results."""
from __future__ import annotations

import ast
import json
import math
import operator
import os
import re
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from .dock import winapi

CACHE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk"
HISTORY = CACHE / "search-history.json"
ICONS = CACHE / "icons"

SETTINGS = [
    ("Display", "ms-settings:display", "screen resolution scale brightness monitor night light"),
    ("Sound", "ms-settings:sound", "audio volume speakers microphone output input"),
    ("Bluetooth & devices", "ms-settings:bluetooth", "bluetooth pair headphones mouse keyboard"),
    ("Wi-Fi", "ms-settings:network-wifi", "wifi wireless network internet"),
    ("Network & internet", "ms-settings:network", "ethernet vpn proxy internet"),
    ("Personalization", "ms-settings:personalization", "theme colors wallpaper background"),
    ("Background", "ms-settings:personalization-background", "wallpaper picture"),
    ("Colors", "ms-settings:colors", "accent dark mode light mode"),
    ("Taskbar", "ms-settings:taskbar", "taskbar"),
    ("Apps & features", "ms-settings:appsfeatures", "uninstall programs installed apps"),
    ("Default apps", "ms-settings:defaultapps", "browser default"),
    ("Startup apps", "ms-settings:startupapps", "startup boot login"),
    ("Accounts", "ms-settings:yourinfo", "account user profile"),
    ("Sign-in options", "ms-settings:signinoptions", "password pin windows hello"),
    ("Date & time", "ms-settings:dateandtime", "clock timezone time"),
    ("Language & region", "ms-settings:regionlanguage", "keyboard language input region"),
    ("Gaming", "ms-settings:gaming-gamebar", "game bar xbox game mode"),
    ("Privacy & security", "ms-settings:privacy", "permissions camera location"),
    ("Windows Update", "ms-settings:windowsupdate", "update upgrade patch"),
    ("Storage", "ms-settings:storagesense", "disk space cleanup storage"),
    ("Power & battery", "ms-settings:powersleep", "sleep power battery screen timeout"),
    ("Notifications", "ms-settings:notifications", "notifications focus do not disturb"),
    ("Mouse", "ms-settings:mousetouchpad", "mouse cursor pointer speed"),
    ("About this PC", "ms-settings:about", "about pc specs name rename"),
    ("Clipboard", "ms-settings:clipboard", "clipboard history"),
    ("Printers & scanners", "ms-settings:printers", "printer scanner"),
    ("Mobile hotspot", "ms-settings:network-mobilehotspot", "hotspot share internet"),
    ("Focus", "ms-settings:focus", "focus session"),
    ("Recovery", "ms-settings:recovery", "reset recovery"),
]

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {name: getattr(math, name) for name in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "floor", "ceil", "radians", "degrees")}
_FUNCS.update(abs=abs, round=round)
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def calculate(text: str):
    """Evaluate plain arithmetic safely; None if it isn't arithmetic."""
    expr = text.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    if not expr or not re.search(r"[\d)]", expr) or not re.fullmatch(r"[\d\s.+\-*/%()a-z_]*", expr.lower()):
        return None
    if re.fullmatch(r"\s*[\d.]+\s*", expr):
        return None  # a lone number is not a calculation

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("too big")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError("unsupported")

    try:
        value = ev(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        value = round(value, 10)
        if value.is_integer():
            value = int(value)
    return value


def score(query: str, name: str) -> float:
    """Prefix > word start > substring > in-order letters."""
    q, n = query.lower().strip(), name.lower()
    if not q:
        return 0
    if n == q:
        return 100
    if n.startswith(q):
        return 90 - len(n) * 0.1
    words = re.split(r"[\s\-_.]+", n)
    if any(w.startswith(q) for w in words):
        return 75 - len(n) * 0.1
    initials = "".join(w[:1] for w in words if w)
    if len(q) >= 2 and initials.startswith(q):
        return 70
    if q in n:
        return 55 - n.index(q) * 0.5
    it = iter(n)
    if len(q) >= 3 and all(c in it for c in q):
        return 30 - len(n) * 0.1
    return 0


class Search(QObject):
    """Exposed to QML as `Search`."""

    resultsChanged = Signal()
    openChanged = Signal()
    indexChanged = Signal()     # the app list was rebuilt (start.py listens)
    iconArrived = Signal()      # one more icon finished rendering
    _apps_ready = Signal("QVariantList")
    _icon_ready = Signal(str, str)

    def __init__(self, store):
        super().__init__()
        self._store = store
        self._apps: list[dict] = []
        self._apps_at = 0.0
        self._loading = False
        self._results: list[dict] = []
        self._query = ""
        self._open = False
        self._screen = 1
        self.screen_at_cursor = lambda: 1  # which screen's dock the hotkey opens search on; set by the app
        self._icons: dict[str, str] = {}
        self._icon_queue: list[tuple[str, str]] = []
        self._icon_lock = threading.Condition()
        self._history = self._load_history()
        self._apps_ready.connect(self._on_apps)
        self._icon_ready.connect(self._on_icon)
        threading.Thread(target=self._icon_worker, daemon=True).start()
        QTimer.singleShot(4000, self.refresh_apps)

    # ---- app index -------------------------------------------------------------

    @Slot()
    def refresh_apps(self):
        if self._loading or time.time() - self._apps_at < 900 and self._apps:
            return
        self._loading = True

        def work():
            apps = []
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                    capture_output=True, timeout=30, creationflags=0x08000000,
                ).stdout.decode("utf-8", "replace")
                data = json.loads(out or "[]")
                if isinstance(data, dict):
                    data = [data]
                seen = set()
                for item in data:
                    name, appid = str(item.get("Name") or "").strip(), str(item.get("AppID") or "").strip()
                    if not name or not appid or name.lower().endswith((".lnk", "uninstall", "readme")) or "uninstall" in name.lower():
                        continue
                    if (name.lower(), appid.lower()) in seen:
                        continue
                    seen.add((name.lower(), appid.lower()))
                    apps.append({"name": name, "appid": appid})
            except Exception as e:
                print(f"[unidesk] app index failed: {e}")
            self._apps_ready.emit(apps)

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList")
    def _on_apps(self, apps):
        self._loading = False
        if apps:
            self._apps = list(apps)
            self._apps_at = time.time()
            self.indexChanged.emit()
        self._run()

    # ---- history ---------------------------------------------------------------

    def _load_history(self) -> dict:
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _remember(self, key: str):
        entry = self._history.get(key, {"count": 0})
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["at"] = time.time()
        self._history[key] = entry
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            HISTORY.write_text(json.dumps(self._history), encoding="utf-8")
        except OSError:
            pass

    # ---- icons -----------------------------------------------------------------

    def _icon(self, appid: str) -> str:
        if appid in self._icons:
            return self._icons[appid]
        self._icons[appid] = ""
        source = appid if re.match(r"^[a-zA-Z]:\\", appid) else f"shell:AppsFolder\\{appid}"
        with self._icon_lock:
            self._icon_queue.append((appid, source))
            self._icon_lock.notify()
        return ""

    def _icon_worker(self):
        winapi.com_init()
        while True:
            with self._icon_lock:
                while not self._icon_queue:
                    self._icon_lock.wait()
                appid, source = self._icon_queue.pop()
            try:
                path = winapi.icon_png(source, 64, ICONS)
            except Exception:
                path = ""
            self._icon_ready.emit(appid, QUrl.fromLocalFile(path).toString() if path else "")

    @Slot(str, str)
    def _on_icon(self, appid: str, url: str):
        if not url:
            return
        self._icons[appid] = url
        self.iconArrived.emit()
        changed = False
        for r in self._results:
            if r.get("appid") == appid:
                r["icon"] = url
                changed = True
        if changed:
            self.resultsChanged.emit()

    # ---- what the Start menu borrows -------------------------------------------

    def app_list(self) -> list[dict]:
        """Every app found, as {name, appid}. Empty until the first index lands."""
        return self._apps

    def icon_for(self, key: str) -> str:
        """The icon for an AppID or a file path: '' now, and iconArrived later."""
        return self._icon(key)

    def most_used(self, want: int) -> list[dict]:
        """The apps opened most often, most first."""
        by_id = {a["appid"]: a for a in self._apps}
        rows = []
        for key, seen in self._history.items():
            app = by_id.get(key[4:]) if key.startswith("app:") else None
            if app:
                rows.append((float(seen.get("count", 0)), float(seen.get("at", 0)), app))
        rows.sort(key=lambda r: (-r[0], -r[1]))
        return [app for _, _, app in rows[:want]]

    def note_launch(self, appid: str):
        """Somebody opened this from Start; it counts the same as from search."""
        self._remember(f"app:{appid}")

    # ---- querying --------------------------------------------------------------

    @Slot(str)
    def setQuery(self, text: str):
        self._query = text
        self._run()

    def _run(self):
        q = self._query.strip()
        results: list[dict] = []
        settings = self._store.config.get("search") or {}

        if not q:
            recent = sorted(((k, v) for k, v in self._history.items() if k.startswith("app:")), key=lambda kv: -float(kv[1].get("at", 0)))[:8]
            by_id = {a["appid"]: a for a in self._apps}
            for key, _ in recent:
                app = by_id.get(key[4:])
                if app:
                    results.append({"kind": "app", "section": "Recent", "title": app["name"], "subtitle": "App",
                                    "appid": app["appid"], "icon": self._icon(app["appid"]), "glyph": ""})
            self._results = results
            self.resultsChanged.emit()
            return

        value = calculate(q)
        if value is not None:
            results.append({"kind": "calc", "section": "Calculator", "title": f"{value:,}" if isinstance(value, int) else str(value),
                            "subtitle": f"{q} =  ·  Enter to copy", "value": str(value), "icon": "", "glyph": "calculate"})

        scored = []
        for app in self._apps:
            s = score(q, app["name"])
            if s <= 0:
                continue
            h = self._history.get(f"app:{app['appid']}")
            if h:
                s += min(20, 4 * float(h.get("count", 0)))
            scored.append((s, app))
        scored.sort(key=lambda sa: -sa[0])
        for _, app in scored[:7]:
            results.append({"kind": "app", "section": "Apps", "title": app["name"], "subtitle": "App",
                            "appid": app["appid"], "icon": self._icon(app["appid"]), "glyph": ""})

        for title, uri, words in SETTINGS:
            s = max(score(q, title), max((score(q, w) for w in words.split()), default=0) * 0.8)
            if s >= 50:
                results.append({"kind": "uri", "section": "Settings", "title": title, "subtitle": "Windows settings",
                                "uri": uri, "icon": "", "glyph": "settings", "score": s})
        # keep the settings section short
        settings_rows = [r for r in results if r["section"] == "Settings"]
        for r in sorted(settings_rows, key=lambda r: -r["score"])[3:]:
            results.remove(r)

        engine = str(settings.get("web", "https://www.google.com/search?q={q}"))
        results.append({"kind": "uri", "section": "More", "title": f"Search the web for “{q}”", "subtitle": urllib.parse.urlparse(engine).netloc,
                        "uri": engine.replace("{q}", urllib.parse.quote_plus(q)), "icon": "", "glyph": "language"})
        results.append({"kind": "uri", "section": "More", "title": f"Search files for “{q}”", "subtitle": "File Explorer",
                        "uri": f"search-ms:query={urllib.parse.quote(q)}&crumb=location:{urllib.parse.quote(str(Path.home()))}",
                        "icon": "", "glyph": "folder"})
        self._results = results
        self.resultsChanged.emit()

    @Property("QVariantList", notify=resultsChanged)
    def results(self):
        return self._results

    @Property(bool, notify=resultsChanged)
    def indexing(self):
        return self._loading and not self._apps

    # ---- actions ---------------------------------------------------------------

    @Slot(int, result=bool)
    def activate(self, index: int) -> bool:
        if not 0 <= index < len(self._results):
            return False
        r = self._results[index]
        try:
            if r["kind"] == "app":
                appid = r["appid"]
                self._remember(f"app:{appid}")
                if re.match(r"^[a-z][a-z0-9+.\-]*://", appid, re.I) or re.match(r"^[a-zA-Z]:\\", appid):
                    os.startfile(appid)
                else:
                    os.startfile(f"shell:AppsFolder\\{appid}")
            elif r["kind"] == "uri":
                os.startfile(r["uri"])
            elif r["kind"] == "calc":
                from PySide6.QtGui import QGuiApplication

                QGuiApplication.clipboard().setText(r["value"])
        except OSError as e:
            print(f"[unidesk] search launch failed: {e}")
            return False
        return True

    # ---- open / close ----------------------------------------------------------

    @Property(bool, notify=openChanged)
    def open(self):
        return self._open

    @Property(int, notify=openChanged)
    def screen(self):
        """The screen whose dock shows search."""
        return self._screen

    @Slot(bool)
    def setOpen(self, on: bool):
        if on == self._open:
            return
        self._open = on
        if on:
            self._query = ""
            self.refresh_apps()
            self._run()
        self.openChanged.emit()

    @Slot()
    def toggle(self):
        if not self._open:
            self._screen = self.screen_at_cursor()
        self.setOpen(not self._open)

    @Slot(int)
    def toggleOn(self, screen: int):
        """The search box on one screen's dock: open there, or close if it's open there already."""
        if self._open and self._screen == screen:
            self.setOpen(False)
        elif self._open:
            self._screen = screen
            self.openChanged.emit()
        else:
            self._screen = screen
            self.setOpen(True)

    @Slot(QObject)
    def focusWindow(self, window):
        """Bring the search window to the front with keyboard focus."""
        try:
            winapi.activate(int(window.winId()), switch=False)  # our own window; no Alt+Tab flash
        except Exception:
            pass
        window.requestActivate()
