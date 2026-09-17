"""Notifications: what Notification Center holds, newest first, read from
Windows' own notification database. Read-only: nothing is changed or
dismissed in Windows; "clear" only hides them from the widget."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import urllib.parse
import winreg
from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QTimer, QUrl, Signal, Slot

from ..dock import winapi

DB = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Notifications" / "wpndatabase.db"
CACHE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk"
ICONS = CACHE / "icons"
STATE = CACHE / "notifications.json"
_FILETIME_EPOCH = 116444736000000000  # 1970-01-01 in 100 ns steps since 1601
# System senders with no Start menu entry to take a name from.
_NAMES = {
    "Windows.Defender.SecurityCenter": "Windows Security",
    "Windows.Defender": "Windows Security",
    "Windows.SystemToast.LowDisk": "Storage",
    "Windows.SystemToast.WindowsUpdate.MoNotification": "Windows Update",
    "Microsoft.Windows.InputSwitchToastHandler": "Keyboard",
}


def parse_toast(payload) -> tuple[str, str, str]:
    """Toast XML -> (title, body, header title)."""
    root = ElementTree.fromstring(payload if isinstance(payload, bytes) else str(payload).encode("utf-8"))
    bindings = root.findall("./visual/binding")
    binding = next((b for b in bindings if b.get("template") == "ToastGeneric"), bindings[0] if bindings else None)
    texts = []
    if binding is not None:
        texts = [(t.text or "").strip() for t in binding.findall("text") if t.get("placement") != "attribution"]
    texts = [t for t in texts if t]
    header = root.find("header")
    header_title = (header.get("title") or "").strip() if header is not None else ""
    return (texts[0] if texts else header_title), "\n".join(texts[1:]), header_title


def read_database(limit: int = 40) -> list[dict] | None:
    """Toasts in Notification Center, newest first; None if there is no database."""
    if not DB.exists():
        return None
    uri = "file:" + urllib.parse.quote(DB.as_posix(), safe="/:") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        rows = con.execute(
            "SELECT n.Id, n.ArrivalTime, n.Payload, h.PrimaryId FROM Notification n "
            "JOIN NotificationHandler h ON h.RecordId = n.HandlerId "
            "WHERE n.Type = 'toast' ORDER BY n.ArrivalTime DESC LIMIT ?", (limit,)).fetchall()
    finally:
        con.close()
    out = []
    for nid, arrival, payload, app_id in rows:
        try:
            title, body, header = parse_toast(payload)
        except (ElementTree.ParseError, TypeError):
            continue
        if title or body:
            out.append({"id": int(nid), "appId": str(app_id or ""), "title": title, "body": body, "header": header,
                        "at": (int(arrival or 0) - _FILETIME_EPOCH) / 10_000})
    return out


def _registered_name(app_id: str) -> str:
    """Apps that register for toasts without a Start menu shortcut put their name here."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{app_id}") as key:
            name = str(winreg.QueryValueEx(key, "DisplayName")[0] or "")
            return "" if name.startswith(("@", "ms-resource:")) else name
    except OSError:
        return ""


def _pretty(app_id: str) -> str:
    """Microsoft.Windows.SomethingHandler -> Something Handler."""
    part = re.split(r"[!_]", app_id)[0].split(".")[-1] or app_id
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", part)


class Notifications(QObject):
    """Exposed to QML as `Notifications`: `items` (newest first: {id, appId, app,
    icon, title, body, at}), `available`, `open(id)`, `openCenter()`, `clear()`."""

    changed = Signal()
    _ready = Signal("QVariant")

    def __init__(self):
        super().__init__()
        self._all: list[dict] = []
        self._items: list[dict] = []
        self._available = True
        self._apps: dict[str, dict] = {}  # app id -> {app, icon, launchable}; filled by the worker
        self._busy = False
        self._again = False
        self._hidden_before = self._load_state()
        self._watcher: QFileSystemWatcher | None = None
        self._poll = QTimer(self, interval=20_000, timeout=self.refresh)
        self._soon = QTimer(self, singleShot=True, interval=500, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def start(self):
        if self._poll.isActive():
            return
        self._poll.start()
        if self._watcher is None and DB.parent.exists():
            # The database changes (its -wal file grows) whenever a notification arrives or goes.
            paths = [str(DB.parent)] + [str(p) for p in (DB, DB.with_name(DB.name + "-wal")) if p.exists()]
            self._watcher = QFileSystemWatcher(paths, self)
            self._watcher.fileChanged.connect(lambda _: self._soon.start())
            self._watcher.directoryChanged.connect(lambda _: self._soon.start())
        self.refresh()

    def stop(self):
        self._poll.stop()
        if self._watcher is not None:
            self._watcher.deleteLater()
            self._watcher = None

    # ---- reading ---------------------------------------------------------------

    @Slot()
    def refresh(self):
        if self._busy:
            self._again = True
            return
        self._busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            rows = read_database()
            if rows is not None:
                winapi.com_init()
                for row in rows:
                    row.update(self._app_info(row["appId"], row["header"]))
                    del row["header"]
        except Exception as e:
            print(f"[unidesk] notifications failed: {e}")
            rows = []
        self._ready.emit(rows)

    def _app_info(self, app_id: str, header: str) -> dict:
        if app_id not in self._apps:
            shell = f"shell:AppsFolder\\{app_id}"
            shell_name = winapi.shell_display_name(shell) if app_id else ""
            try:
                icon = winapi.icon_png(shell, 64, ICONS) if shell_name else ""
            except Exception:
                icon = ""
            name = _registered_name(app_id) or shell_name or _NAMES.get(app_id) or header or _pretty(app_id)
            self._apps[app_id] = {"app": name, "icon": QUrl.fromLocalFile(icon).toString() if icon else "",
                                  "launchable": bool(shell_name)}
        return dict(self._apps[app_id])

    @Slot("QVariant")
    def _on_ready(self, rows):
        self._busy = False
        available = rows is not None
        force = available != self._available
        self._available = available
        self._all = list(rows or [])
        self._publish(force=force)
        if self._again:
            self._again = False
            self.refresh()

    def _publish(self, force: bool = False):
        items = [n for n in self._all if n["at"] > self._hidden_before]
        if force or items != self._items:
            self._items = items
            self.changed.emit()

    # ---- hidden ("cleared") --------------------------------------------------------

    @staticmethod
    def _load_state() -> float:
        try:
            return float(json.loads(STATE.read_text(encoding="utf-8")).get("hidden_before", 0))
        except (OSError, ValueError, AttributeError):
            return 0.0

    # ---- QML -------------------------------------------------------------------

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property(bool, notify=changed)
    def available(self):
        return self._available

    @Slot(int)
    def open(self, notification_id: int):
        """Open the app that sent it, or Notification Center when that isn't possible."""
        item = next((n for n in self._items if n["id"] == notification_id), None)
        if item and item.get("launchable"):
            try:
                os.startfile(f"shell:AppsFolder\\{item['appId']}")
                return
            except OSError:
                pass
        self.openCenter()

    @Slot()
    def openCenter(self):
        winapi.tap(winapi.VK_LWIN, ord("N"))

    @Slot()
    def clear(self):
        """Hide everything shown now; newer notifications still appear."""
        if not self._all:
            return
        self._hidden_before = max(n["at"] for n in self._all)
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"hidden_before": self._hidden_before}), encoding="utf-8")
        except OSError:
            pass
        self._publish()
