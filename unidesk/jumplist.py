"""The jump list Windows shows when you right-click an app on the taskbar.

Two different things are stitched together here, because Windows stores them
apart:

* **Recent and frequent documents** come from the shell, through
  `IApplicationDocumentLists`. It takes the app's AppUserModelID and hands back
  the same items Explorer would show.
* **Tasks and the app's own categories** - "New window", VS Code's recent
  *folders*, a browser's private window - are written by the app itself into
  `%APPDATA%\\Microsoft\\Windows\\Recent\\CustomDestinations\\<hash>.customDestinations-ms`,
  which is a run of shell links with no API to read it. We parse it.

The file is named after a hash of the AppUserModelID that Microsoft never
documented, so instead of guessing the polynomial we index the folder once by
the executable each link points at. There are only a few dozen files and the
index is cached until one of them changes.

Nothing here writes anything; every entry ends up as an executable plus
arguments, run exactly the way the real jump list runs it.
"""
from __future__ import annotations

import ctypes
import io
import os
import time
from ctypes import POINTER, byref, c_int, c_uint, c_void_p, c_wchar_p
from pathlib import Path

# ---- the shell's recent / frequent list -------------------------------------------------

_ADLT_RECENT, _ADLT_FREQUENT = 0, 1
_SIGDN_NORMALDISPLAY = 0
_SIGDN_FILESYSPATH = 0x80058000

_CLSID_ApplicationDocumentLists = "{86BEC222-30F2-47E0-9F25-60D11CD75C28}"


def _interfaces():
    """Defined lazily: importing comtypes costs more than most runs need."""
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    class IShellItem(IUnknown):
        _iid_ = GUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
        _methods_ = [
            COMMETHOD([], HRESULT, "BindToHandler",
                      (["in"], c_void_p, "pbc"), (["in"], POINTER(GUID), "bhid"),
                      (["in"], POINTER(GUID), "riid"), (["out"], POINTER(c_void_p), "ppv")),
            COMMETHOD([], HRESULT, "GetParent", (["out"], POINTER(POINTER(IUnknown)), "ppsi")),
            COMMETHOD([], HRESULT, "GetDisplayName",
                      (["in"], c_uint, "sigdnName"), (["out"], POINTER(c_wchar_p), "ppszName")),
            COMMETHOD([], HRESULT, "GetAttributes",
                      (["in"], c_uint, "sfgaoMask"), (["out"], POINTER(c_uint), "psfgaoAttribs")),
            COMMETHOD([], HRESULT, "Compare",
                      (["in"], POINTER(IUnknown), "psi"), (["in"], c_uint, "hint"),
                      (["out"], POINTER(c_int), "piOrder")),
        ]

    class IObjectArray(IUnknown):
        _iid_ = GUID("{92CA9DCD-5622-4BBA-A805-5E9F541BD8C9}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint), "pcObjects")),
            COMMETHOD([], HRESULT, "GetAt",
                      (["in"], c_uint, "uiIndex"), (["in"], POINTER(GUID), "riid"),
                      (["out"], POINTER(c_void_p), "ppv")),
        ]

    class IApplicationDocumentLists(IUnknown):
        _iid_ = GUID("{3C594F9F-9F30-47A1-979A-C9E83D3D0A06}")
        _methods_ = [
            COMMETHOD([], HRESULT, "SetAppID", (["in"], c_wchar_p, "pszAppID")),
            COMMETHOD([], HRESULT, "GetList",
                      (["in"], c_uint, "listtype"), (["in"], c_uint, "cItemsDesired"),
                      (["in"], POINTER(GUID), "riid"), (["out"], POINTER(c_void_p), "ppv")),
        ]

    return comtypes, IShellItem, IObjectArray, IApplicationDocumentLists


def _documents(aumid: str, which: int, want: int) -> list[dict]:
    if not aumid:
        return []
    try:
        import comtypes.client

        comtypes, IShellItem, IObjectArray, IApplicationDocumentLists = _interfaces()
        lists = comtypes.client.CreateObject(
            _CLSID_ApplicationDocumentLists, interface=IApplicationDocumentLists
        )
        lists.SetAppID(aumid)
        raw = lists.GetList(which, want, byref(IObjectArray._iid_))
        if not raw:
            return []
        array = ctypes.cast(raw, POINTER(IObjectArray))
        out: list[dict] = []
        for i in range(array.GetCount()):
            try:
                item = ctypes.cast(array.GetAt(i, byref(IShellItem._iid_)), POINTER(IShellItem))
                try:
                    path = item.GetDisplayName(_SIGDN_FILESYSPATH)
                except Exception:
                    path = ""
                if not path:
                    continue
                out.append({"title": item.GetDisplayName(_SIGDN_NORMALDISPLAY) or Path(path).name,
                            "subtitle": str(Path(path).parent), "target": path})
            except Exception:
                continue
        return out
    except Exception:
        return []  # no jump list is not an error; the menu simply has fewer rows


# ---- the app's own tasks and categories -------------------------------------------------

# every shell link starts with its header size and the link CLSID
_LNK_SIGNATURE = bytes(
    [0x4C, 0, 0, 0, 0x01, 0x14, 0x02, 0x00, 0, 0, 0, 0, 0xC0, 0, 0, 0, 0, 0, 0, 0x46]
)


def _custom_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent" / "CustomDestinations"


_index: dict[str, list[Path]] = {}
_index_stamp: tuple[float, int] = (0.0, 0)


def _custom_files_for(exe: str) -> list[Path]:
    """Which .customDestinations-ms files hold links to this executable.

    Microsoft names them after an undocumented hash of the AppUserModelID, so we
    read the folder instead and remember what pointed where.
    """
    global _index, _index_stamp
    folder = _custom_dir()
    if not folder.is_dir():
        return []
    try:
        files = sorted(folder.glob("*.customDestinations-ms"))
        stamp = (max((f.stat().st_mtime for f in files), default=0.0), len(files))
    except OSError:
        return []
    if stamp != _index_stamp:
        fresh: dict[str, list[Path]] = {}
        for f in files:
            try:
                blob = f.read_bytes().lower()
            except OSError:
                continue
            for name in {b for b in _exe_names(blob)}:
                fresh.setdefault(name, []).append(f)
        _index, _index_stamp = fresh, stamp
    return _index.get(Path(exe).name.lower(), [])


def _exe_names(blob: bytes) -> set[str]:
    """Executable names mentioned in a custom-destinations file, utf-16 and ansi."""
    found: set[str] = set()
    for text in (blob.decode("utf-16-le", "ignore"), blob.decode("latin-1", "ignore")):
        lowered = text.lower()
        start = 0
        while True:
            hit = lowered.find(".exe", start)
            if hit < 0:
                break
            head = lowered.rfind("\\", 0, hit)
            name = lowered[head + 1: hit + 4] if head >= 0 else lowered[max(0, hit - 40): hit + 4]
            if name and len(name) < 64:
                found.add(name)
            start = hit + 4
    return found


def _tasks(exe: str, want: int) -> list[dict]:
    try:
        import pylnk3
    except Exception:
        return []
    out: list[dict] = []
    for path in _custom_files_for(exe):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        offset = 0
        while len(out) < want:
            offset = raw.find(_LNK_SIGNATURE, offset)
            if offset < 0:
                break
            try:
                link = pylnk3.Lnk(io.BytesIO(raw[offset:]))
                target = ""
                try:
                    target = link.path or ""
                except Exception:
                    pass
                args = (link.arguments or "").strip()
                # left empty on purpose when the app wrote none: the caller
                # derives a better label than this executable's own name.
                title = (link.description or "").strip()
                if target and (args or title):
                    out.append({"title": title, "args": args, "target": target})
            except Exception:
                pass
            offset += 4
    return out


# ---- what the dock asks for -------------------------------------------------------------

_cache: dict[str, tuple[float, list[dict]]] = {}
_TTL = 20.0


def _destination(args: str) -> str:
    """The file, folder or address an argument list points at, if it points at one.

    This is what separates one of the app's verbs ("New window", `-n`) from a
    place it remembers ("--folder-uri file:///c%3A/..."), which the file itself
    gives us no flag for.
    """
    text = (args or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for scheme in ("file:///", "http://", "https://"):
        hit = lowered.find(scheme)
        if hit >= 0:
            return text[hit:].strip('"').split(" ")[0]
    # a drive letter or a UNC path, quoted or bare
    for i in range(len(text) - 2):
        if text[i + 1] == ":" and text[i + 2] in "\\/" and text[i].isalpha():
            return text[i:].strip('"')
    if "\\\\" in text:
        return text[text.index("\\\\"):].strip('"')
    return ""


def _readable(destination: str) -> str:
    """A short label for a destination, so a row is not just the app's own name."""
    value = destination
    if value.startswith("file:///"):
        from urllib.parse import unquote

        value = unquote(value[8:]).replace("/", "\\")
    if value.startswith("http://") or value.startswith("https://"):
        rest = value.split("://", 1)[1]
        host, _, path = rest.partition("/")
        host = host[4:] if host.startswith("www.") else host
        leaf = path.strip("/").split("/")[-1] if path.strip("/") else ""
        return f"{host}/{leaf}" if leaf and len(leaf) < 28 else host
    value = value.rstrip("\\/")
    return Path(value).name or value


def entries(exe: str, aumid: str = "", limit: int = 9) -> list[dict]:
    """Rows for one app's menu: its own tasks first, then what it opened lately.

    Each row is {title, subtitle, kind, target, args}: `kind` is 'task' for
    something the app offers and 'recent' for a document, and the pair
    (target, args) is what `open_entry` runs.
    """
    exe = str(exe or "")
    key = f"{exe}|{aumid}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]

    rows: list[dict] = []
    seen: set[str] = set()

    for task in _tasks(exe, limit):
        mark = f"{task['target']}|{task['args']}".lower()
        if mark in seen:
            continue
        seen.add(mark)
        # Arguments that name a place make it somewhere the app remembers;
        # arguments that name none make it one of the app's own verbs.
        destination = _destination(task["args"])
        written = task["title"]
        if written and ("\\" in written or "/" in written):
            # apps that name the place itself: lead with the folder, the way
            # Windows does, and keep the full path underneath
            title, subtitle = _readable(written), written
        elif written:
            title, subtitle = written, ""
        elif destination:
            title, subtitle = _readable(destination), ""
        else:
            # a verb the app named nothing: its own switch reads better than
            # the executable ("--incognito" -> "Incognito")
            flag = next((p for p in task["args"].split() if p.startswith("-")), "")
            flag = flag.lstrip("-").split("=")[0].replace("-", " ").strip()
            title, subtitle = (flag.capitalize() if flag else Path(task["target"]).stem), ""
        rows.append({
            "title": title,
            "subtitle": subtitle,
            "kind": "recent" if destination else "task",
            "target": task["target"],
            "args": task["args"],
        })

    if len(rows) < limit:
        for doc in _documents(aumid, _ADLT_RECENT, limit):
            mark = doc["target"].lower()
            if mark in seen:
                continue
            seen.add(mark)
            rows.append({
                "title": doc["title"],
                "subtitle": doc["subtitle"],
                "kind": "recent",
                # opened with the app it belongs to, the way the real list does it
                "target": exe or doc["target"],
                "args": f'"{doc["target"]}"' if exe else "",
            })
            if len(rows) >= limit:
                break

    _cache[key] = (now, rows)
    return rows


def open_entry(target: str, args: str = "") -> bool:
    """Run one row. ShellExecute so quoting and elevation behave as Explorer's."""
    target = os.path.expandvars(str(target or "").strip())
    if not target:
        return False
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "open", target, (args or None), None, 1
        )
        return int(result) > 32
    except Exception:
        return False
