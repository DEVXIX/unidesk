"""Saved connections, and the passwords that go with them.

A password typed into a widget has to go somewhere if "save" is ticked, and
the two obvious places are both wrong: the config file is meant to be readable
(and pasteable into an issue), and a plain file beside it is a password in
plain sight.

So the secret parts go through DPAPI - Windows' own per-user encryption. What
is written can only be decrypted by this Windows account on this machine, and
unidesk never holds a key of its own. Everything else about a connection (its
name, host, port, user) stays readable, because that is not what needs hiding
and a file you cannot read is a file you cannot fix.

Nothing here is specific to ssh. A connection has a `kind`, and the S3 pane
keeps its keys in exactly the same place.
"""
from __future__ import annotations

import base64
import ctypes
import json
from ctypes import wintypes

from .config import CONFIG_DIR

STORE = CONFIG_DIR / "connections.json"

crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _take(blob: _Blob) -> bytes:
    out = ctypes.string_at(blob.pbData, blob.cbData)
    kernel32.LocalFree(blob.pbData)
    return out


def protect(text: str) -> str:
    """Encrypted for this Windows account, as text that fits in a JSON file."""
    if not text:
        return ""
    out = _Blob()
    source = _blob(text.encode("utf-8"))
    if not crypt32.CryptProtectData(ctypes.byref(source), "unidesk", None, None, None,
                                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError(f"could not encrypt: {ctypes.get_last_error()}")
    return base64.b64encode(_take(out)).decode("ascii")


def unprotect(stored: str) -> str:
    """Back again, or "" if this is not our account or the file was tampered with."""
    if not stored:
        return ""
    out = _Blob()
    try:
        source = _blob(base64.b64decode(stored))
    except ValueError:
        return ""
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        return ""
    return _take(out).decode("utf-8", "replace")


class Vault:
    """The saved connections. Secrets go in and out encrypted; everything the
    widget shows you is plain."""

    def __init__(self):
        self._entries: list[dict] = self._read()

    def _read(self) -> list[dict]:
        try:
            data = json.loads(STORE.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    def _write(self):
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            STORE.write_text(json.dumps(self._entries, indent=2), "utf-8")
        except OSError as e:
            print(f"[unidesk] connections could not be saved: {e}")

    # ---- reading ----------------------------------------------------------

    def listing(self, kind: str = "") -> list[dict]:
        """Everything but the secrets, for showing in a list."""
        return [
            {k: v for k, v in entry.items() if k != "secrets"}
            for entry in self._entries
            if not kind or entry.get("kind") == kind
        ]

    def find(self, name: str, kind: str = "") -> dict | None:
        for entry in self._entries:
            if entry.get("name") == name and (not kind or entry.get("kind") == kind):
                return entry
        return None

    def secrets(self, name: str) -> dict:
        """The decrypted secret fields of one connection."""
        entry = self.find(name)
        if not entry:
            return {}
        stored = entry.get("secrets")
        if not isinstance(stored, str):
            return {}
        try:
            return json.loads(unprotect(stored) or "{}")
        except ValueError:
            return {}

    # ---- writing ----------------------------------------------------------

    def save(self, entry: dict, secrets: dict) -> str:
        """Add or replace one connection. Answers the name it was filed under."""
        name = str(entry.get("name") or entry.get("host") or "connection").strip()
        record = {k: v for k, v in entry.items() if k != "secrets"}
        record["name"] = name
        if any(secrets.values()):
            try:
                record["secrets"] = protect(json.dumps(secrets))
            except OSError as e:
                print(f"[unidesk] the password was not saved: {e}")
        existing = self.find(name)
        if existing:
            self._entries[self._entries.index(existing)] = record
        else:
            self._entries.append(record)
        self._write()
        return name

    def rename(self, name: str, called: str) -> bool:
        """Call one of these something else, keeping what it knows.

        The secrets are moved across still encrypted - they are never unpacked
        to be carried from one name to the other.
        """
        called = str(called or "").strip()
        entry = self.find(name)
        if not entry or not called or called == name:
            return False
        if self.find(called):
            return False        # something is already called that
        entry["name"] = called
        self._write()
        return True

    def forget(self, name: str):
        entry = self.find(name)
        if entry:
            self._entries.remove(entry)
            self._write()
