"""unidesk's own Start menu: the Windows 11 layout, in the desk's theme.

Windows' own Start cannot be restyled - it is a packaged shell surface and
nothing outside it gets to draw there - so this is a replacement rather than a
reskin. The shape is kept exactly: a search box, a page of pinned apps with
dots down the side, what you opened lately, and your name beside the power
button. What changes is everything it is drawn with - the desk's colours,
font, shapes and hover feel.

Most of what Start needs already exists in search.py: the app index (one
`Get-StartApps` run), icons rendered on a worker thread, and how often you open
things. This module adds the three lists Start has that search does not:

* **Pinned** - kept in start-pinned.json. Windows keeps its own pinned list in
  a packaged database that only Start may read, so the first list is seeded
  from apps you actually have and use, and is yours to arrange after that.
* **Recommended** - what was installed lately (Start menu shortcuts by age) and
  what you opened lately (the shell's Recent folder).
* **You** - the name and round picture Windows shows on the sign-in screen.

Icons are not carried in the lists. A row knows its key - an AppID for an app,
a path for a file - and QML asks `iconFor(key)` for the ones actually on
screen, so opening "All apps" does not queue two hundred icon renders.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from .dock import winapi
from .search import CACHE

PINS = CACHE / "start-pinned.json"
RECENT = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
PROGRAMS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
)
NEW_FOR_DAYS = 14
PER_PAGE = 18  # six across, three down, like Windows

# What the first page is made of when there is nothing to go on yet: the apps
# most people reach for, in the order Start would put them, keeping only the
# ones this machine actually has. Anything left over is filled in with what
# unidesk has watched you open.
FAVOURITES = (
    "Opera", "Opera GX", "Microsoft Edge", "Google Chrome", "Firefox",
    "File Explorer", "Settings", "Microsoft Store", "Mail", "Calendar",
    "Photos", "Calculator", "Notepad", "Terminal", "Windows Terminal",
    "Visual Studio Code", "Spotify", "Discord", "Steam", "Xbox",
    "Media Player", "Clock", "Snipping Tool", "Paint", "Task Manager",
)

POWER = {
    "shutdown": ("shutdown", "/s", "/t", "0"),
    "restart": ("shutdown", "/r", "/t", "0"),
    "signout": ("shutdown", "/l"),
}


# ---- who you are ----------------------------------------------------------------------


def _sid() -> str:
    """This account's security identifier, which is how Windows files things per user.

    The types are spelled out rather than left to ctypes: a handle passed as a
    plain int is truncated to 32 bits on a 64-bit build, and the call then asks
    about a process that does not exist.
    """
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return ""
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        if not size.value:
            return ""
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, 1, buf, size.value, ctypes.byref(size)):
            return ""
        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first field is the SID.
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        out = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(out)):
            return ""
        text = out.value or ""
        kernel32.LocalFree(ctypes.cast(out, ctypes.c_void_p))
        return text
    except OSError:
        return ""
    finally:
        kernel32.CloseHandle(token)


def display_name() -> str:
    """Your name as Windows shows it - the full one where there is one.

    A Microsoft account's real name lives with the credential provider, which
    nothing outside the sign-in screen may read, so this often comes back as
    the account name. `start: {name: ...}` in config.yaml settles it.
    """
    try:
        secur32 = ctypes.WinDLL("secur32", use_last_error=True)
        size = wintypes.ULONG(0)
        secur32.GetUserNameExW(3, None, ctypes.byref(size))  # NameDisplay
        buf = ctypes.create_unicode_buffer(max(size.value, 256))
        size = wintypes.ULONG(len(buf))
        if secur32.GetUserNameExW(3, buf, ctypes.byref(size)) and (buf.value or "").strip():
            return buf.value.strip()
    except OSError:
        pass
    return os.environ.get("USERNAME", "")


def account_picture() -> str:
    """The round picture next to your name, as a file URL, or '' if there is none."""
    sid = _sid()
    best = ""
    if sid:
        import winreg

        try:
            key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\AccountPicture\Users\{sid}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                sizes: dict[int, str] = {}
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, i)
                    if not name.startswith("Image") or not name[5:].isdigit():
                        continue
                    if isinstance(value, str) and value and Path(value).exists():
                        sizes[int(name[5:])] = value
            # Big enough not to look soft at 48 points, small enough to decode fast.
            for wanted in sorted(sizes):
                if wanted >= 192:
                    best = sizes[wanted]
                    break
            if not best and sizes:
                best = sizes[max(sizes)]
        except OSError:
            pass
    if not best:
        folders = [Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "AccountPictures"]
        if sid:
            folders.append(Path("C:/Users/Public/AccountPictures") / sid)
        for folder in folders:
            try:
                pictures = [p for p in folder.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")]
            except OSError:
                continue
            if pictures:
                best = str(max(pictures, key=lambda p: p.stat().st_size))
                break
    return QUrl.fromLocalFile(best).toString() if best else ""


def initials(name: str) -> str:
    """Two letters for when there is no picture."""
    parts = [p for p in str(name).replace("_", " ").split() if p[:1].isalnum()]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


# ---- what you opened, and what turned up ------------------------------------------------


def ago(when: float) -> str:
    gap = max(0.0, time.time() - when)
    if gap < 90:
        return "Just now"
    if gap < 3600:
        return f"{int(gap // 60)} min ago"
    if gap < 7200:
        return "An hour ago"
    if gap < 86400:
        return f"{int(gap // 3600)} hours ago"
    if gap < 172800:
        return "Yesterday"
    if gap < 7 * 86400:
        return f"{int(gap // 86400)} days ago"
    return time.strftime("%d %b", time.localtime(when))


def recent_files(limit: int = 10) -> list[dict]:
    """What you opened lately, from the shell's own Recent folder.

    These are shortcuts, so they open with os.startfile as they are - there is
    no need to read where each one points before it can be listed.
    """
    try:
        entries = [e for e in os.scandir(RECENT) if e.name.lower().endswith(".lnk") and e.is_file()]
    except OSError:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=lambda e: -e.stat().st_mtime):
        title = entry.name[:-4]
        if not title or title.lower() in seen:
            continue
        # Shell leftovers - "ms-screenclip---source=PrintScreen (240)" and
        # friends - are protocol handlers the shell noted, not documents.
        if title.lower().startswith("ms-") or "---" in title:
            continue
        seen.add(title.lower())
        out.append({"kind": "file", "title": title, "subtitle": ago(entry.stat().st_mtime),
                    "key": entry.path, "target": entry.path})
        if len(out) >= limit:
            break
    return out


def fresh_apps(days: int = NEW_FOR_DAYS, limit: int = 4) -> list[dict]:
    """Apps whose Start menu shortcut turned up in the last fortnight."""
    cut = time.time() - days * 86400
    found: list[tuple[float, str]] = []
    for root in PROGRAMS:
        try:
            for path in root.rglob("*.lnk"):
                try:
                    at = path.stat().st_mtime
                except OSError:
                    continue
                if at >= cut and "uninstall" not in path.stem.lower():
                    found.append((at, path.stem))
        except OSError:
            continue
    out: list[dict] = []
    seen: set[str] = set()
    for at, name in sorted(found, reverse=True):
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "at": at})
        if len(out) >= limit:
            break
    return out


class Start(QObject):
    """Exposed to QML as `Start`."""

    pinnedChanged = Signal()
    appsChanged = Signal()
    recommendedChanged = Signal()
    iconsChanged = Signal()
    openChanged = Signal()
    userChanged = Signal()
    _scanned = Signal("QVariantList", "QVariantList")
    _found_you = Signal(str, str)

    def __init__(self, store, search):
        super().__init__()
        self._store = store
        self._search = search
        self._pins: list[dict] = self._load_pins()
        self._seeded = bool(self._pins)
        self._recent: list[dict] = []
        self._fresh: list[dict] = []
        self._scanning = False
        self._scanned_at = 0.0
        self._icon_rev = 0
        self._open = False
        self._screen = 1
        self.screen_at_cursor = lambda: 1  # set by the app, as search does
        self._name = ""
        self._picture = ""

        self._scanned.connect(self._on_scan)
        self._found_you.connect(self._set_who)
        search.indexChanged.connect(self._on_index)
        search.iconArrived.connect(self._icons_landed)
        # Icons arrive one at a time off a worker thread; tell QML in batches.
        self._icon_beat = QTimer(self)
        self._icon_beat.setSingleShot(True)
        self._icon_beat.setInterval(120)
        self._icon_beat.timeout.connect(self._bump_icons)
        QTimer.singleShot(1200, self._who)
        QTimer.singleShot(5000, self.rescan)

    # ---- the pinned list -------------------------------------------------------

    def _load_pins(self) -> list[dict]:
        try:
            saved = json.loads(PINS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for row in saved if isinstance(saved, list) else []:
            if isinstance(row, dict) and row.get("appid"):
                out.append({"name": str(row.get("name") or ""), "appid": str(row["appid"])})
        return out

    def _save_pins(self):
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            spare = PINS.with_suffix(".json.tmp")
            spare.write_text(json.dumps(self._pins, indent=1), encoding="utf-8")
            os.replace(spare, PINS)
        except OSError as e:
            print(f"[unidesk] start: could not save the pinned apps: {e}")

    def _seed(self):
        """A first page for somebody who has never arranged one.

        Only ever run once, and only once the app index has arrived - seeding
        from an empty index would write an empty list and call it a choice.
        """
        index = self._search.app_list()
        if self._seeded or not index:
            return
        by_name = {a["name"].lower(): a for a in index}
        picked: list[dict] = []
        taken: set[str] = set()
        for wanted in FAVOURITES:
            app = by_name.get(wanted.lower())
            if app and app["appid"] not in taken:
                taken.add(app["appid"])
                picked.append({"name": app["name"], "appid": app["appid"]})
        for app in self._search.most_used(PER_PAGE):
            if len(picked) >= PER_PAGE:
                break
            if app["appid"] not in taken:
                taken.add(app["appid"])
                picked.append({"name": app["name"], "appid": app["appid"]})
        self._pins = picked[:PER_PAGE]
        self._seeded = True
        self._save_pins()
        self.pinnedChanged.emit()

    def _index_of(self, appid: str) -> int:
        for i, row in enumerate(self._pins):
            if row["appid"] == appid:
                return i
        return -1

    @Property("QVariantList", notify=pinnedChanged)
    def pinned(self):
        """The pinned apps, named from the index where it knows better.

        A pin whose app is not in the index is still listed under the name it
        was pinned with: hiding it would leave something unpinnable on a page
        you cannot see.
        """
        by_id = {a["appid"]: a for a in self._search.app_list()}
        out = []
        for row in self._pins:
            app = by_id.get(row["appid"])
            out.append({"name": (app or row).get("name") or row["appid"],
                        "appid": row["appid"], "key": row["appid"],
                        "removable": True})
        return out

    @Property(int, notify=pinnedChanged)
    def pages(self):
        return max(1, -(-len(self._pins) // PER_PAGE))

    @Property(int, constant=True)
    def perPage(self):
        return PER_PAGE

    @Slot(str, result=bool)
    def isPinned(self, appid: str) -> bool:
        return self._index_of(str(appid)) >= 0

    @Slot(str, str)
    def pin(self, appid: str, name: str = ""):
        appid = str(appid or "")
        if not appid or self._index_of(appid) >= 0:
            return
        self._pins.append({"name": str(name or appid), "appid": appid})
        self._save_pins()
        self.pinnedChanged.emit()

    @Slot(str)
    def unpin(self, appid: str):
        at = self._index_of(str(appid))
        if at < 0:
            return
        self._pins.pop(at)
        self._save_pins()
        self.pinnedChanged.emit()

    @Slot(str)
    def moveToFront(self, appid: str):
        at = self._index_of(str(appid))
        if at <= 0:
            return
        self._pins.insert(0, self._pins.pop(at))
        self._save_pins()
        self.pinnedChanged.emit()

    @Slot(int, int)
    def movePin(self, at: int, to: int):
        """Drag one pin onto another's place."""
        if not (0 <= at < len(self._pins)) or not (0 <= to < len(self._pins)) or at == to:
            return
        self._pins.insert(to, self._pins.pop(at))
        self._save_pins()
        self.pinnedChanged.emit()

    # ---- all apps, and what to recommend ---------------------------------------

    @Property("QVariantList", notify=appsChanged)
    def apps(self):
        """Every app, alphabetically, under the letter it starts with."""
        out = []
        for app in sorted(self._search.app_list(), key=lambda a: a["name"].lower()):
            first = app["name"][:1].upper()
            out.append({"name": app["name"], "appid": app["appid"], "key": app["appid"],
                        "section": first if first.isalpha() else "#"})
        return out

    def _rows(self) -> list[dict]:
        """What turned up lately, then what you opened lately."""
        by_name = {a["name"].lower(): a for a in self._search.app_list()}
        pinned = {row["appid"] for row in self._pins}
        out = []
        for app in self._fresh:
            found = by_name.get(app["name"].lower())
            if not found or found["appid"] in pinned:
                continue
            out.append({"kind": "app", "title": found["name"], "subtitle": "Recently added",
                        "key": found["appid"], "target": found["appid"]})
        out.extend(dict(row) for row in self._recent)
        return out

    @Property("QVariantList", notify=recommendedChanged)
    def recommended(self):
        """The six that fit on the home page."""
        return self._rows()[:6]

    @Property("QVariantList", notify=recommendedChanged)
    def history(self):
        """All of them, for the More page."""
        return self._rows()

    @Slot()
    def rescan(self):
        """Read the Recent folder and the Start menu folders, off the GUI thread."""
        if self._scanning or time.time() - self._scanned_at < 20:
            return
        self._scanning = True

        def work():
            try:
                found, new = recent_files(20), fresh_apps()
            except Exception as e:  # a folder that cannot be read is not worth a crash
                print(f"[unidesk] start: could not read what you opened lately: {e}")
                found, new = [], []
            self._scanned.emit(found, new)

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList", "QVariantList")
    def _on_scan(self, found, new):
        self._scanning = False
        self._scanned_at = time.time()
        self._recent = [dict(r) for r in found]
        self._fresh = [dict(r) for r in new]
        self.recommendedChanged.emit()

    @Slot()
    def _on_index(self):
        self._seed()
        self.pinnedChanged.emit()
        self.appsChanged.emit()
        self.recommendedChanged.emit()

    # ---- icons -----------------------------------------------------------------

    @Slot(str, result=str)
    def iconFor(self, key: str) -> str:
        """The icon for one row, asked for by whatever is on screen."""
        return self._search.icon_for(str(key))

    @Property(int, notify=iconsChanged)
    def iconRevision(self):
        """Bumped whenever icons land, so bindings that call iconFor run again."""
        return self._icon_rev

    @Slot()
    def _icons_landed(self):
        if not self._icon_beat.isActive():
            self._icon_beat.start()

    def _bump_icons(self):
        self._icon_rev += 1
        self.iconsChanged.emit()

    # ---- you -------------------------------------------------------------------

    def _who(self):
        chosen = str((self._store.config.get("start") or {}).get("name") or "").strip()

        def work():
            self._found_you.emit(chosen or display_name(), account_picture())

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str)
    def _set_who(self, name: str, picture: str):
        self._name, self._picture = name, picture
        self.userChanged.emit()

    @Property("QVariantMap", notify=userChanged)
    def user(self):
        return {"name": self._name or os.environ.get("USERNAME", ""),
                "picture": self._picture,
                "initials": initials(self._name or os.environ.get("USERNAME", "?"))}

    # ---- doing things ----------------------------------------------------------

    @Slot(str, result=bool)
    def launch(self, appid: str) -> bool:
        appid = str(appid or "")
        if not appid:
            return False
        try:
            winapi.user32.AllowSetForegroundWindow(-1)  # let what we start come to the front
            self._search.note_launch(appid)
            if appid[1:3] == ":\\" or "://" in appid:
                os.startfile(appid)
            else:
                os.startfile(f"shell:AppsFolder\\{appid}")
            return True
        except OSError as e:
            print(f"[unidesk] start: {appid} would not open: {e}")
            return False

    @Slot(str, result=bool)
    def openPath(self, target: str) -> bool:
        try:
            winapi.user32.AllowSetForegroundWindow(-1)
            os.startfile(str(target))
            return True
        except OSError as e:
            print(f"[unidesk] start: {target} would not open: {e}")
            return False

    @Slot(str)
    def openLocation(self, appid: str):
        """Show where the app lives - its folder for a program, the apps folder otherwise."""
        appid = str(appid or "")
        try:
            if appid[1:3] == ":\\" and Path(appid).exists():
                subprocess.Popen(["explorer", "/select,", appid])
            else:
                os.startfile("shell:AppsFolder")
        except OSError as e:
            print(f"[unidesk] start: could not show where {appid} is: {e}")

    @Slot(str, result=bool)
    def canRunAsAdmin(self, appid: str) -> bool:
        """Only a real program on disk can be asked for; Store apps cannot."""
        return str(appid or "")[1:3] == ":\\"

    @Slot(str)
    def runAsAdmin(self, appid: str):
        if not self.canRunAsAdmin(appid):
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", str(appid), None, None, 1)
        except OSError as e:
            print(f"[unidesk] start: could not run {appid} as administrator: {e}")

    @Slot(str)
    def uninstall(self, appid: str):
        try:
            os.startfile("ms-settings:appsfeatures")
        except OSError:
            pass

    @Slot()
    def accountSettings(self):
        try:
            os.startfile("ms-settings:yourinfo")
        except OSError:
            pass

    @Slot(str)
    def power(self, what: str):
        """Lock, sign out, sleep, restart or shut down.

        Nothing here asks twice: these are the buttons somebody came to Start
        to press, and Windows' own menu does not ask either.
        """
        what = str(what or "").lower()
        self.setOpen(False)
        try:
            if what == "lock":
                ctypes.windll.user32.LockWorkStation()
            elif what == "sleep":
                # Sleep rather than hibernate, and do not let an app veto it.
                ctypes.windll.powrprof.SetSuspendState(False, True, False)
            elif what in POWER:
                subprocess.Popen(POWER[what], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                print(f"[unidesk] start: no such power button: {what!r}")
        except OSError as e:
            print(f"[unidesk] start: {what} failed: {e}")

    # ---- open / close ----------------------------------------------------------

    @Property(bool, notify=openChanged)
    def open(self):
        return self._open

    @Property(int, notify=openChanged)
    def screen(self):
        return self._screen

    @Slot(bool)
    def setOpen(self, on: bool):
        on = bool(on)
        if on == self._open:
            return
        self._open = on
        if on:
            self._search.refresh_apps()
            self._seed()
            self.rescan()
            self._who()
        self.openChanged.emit()

    @Slot()
    def toggle(self):
        if not self._open:
            self._screen = self.screen_at_cursor()
        self.setOpen(not self._open)

    @Slot(int)
    def toggleOn(self, screen: int):
        """The Start button on one screen's dock: open there, or close if it is open there."""
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
        try:
            winapi.activate(int(window.winId()), switch=False)  # our own window; no Alt+Tab flash
        except Exception:
            pass
        window.requestActivate()
