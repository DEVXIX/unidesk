"""S3 buckets on the desk - Amazon's, MinIO's, or anything else that speaks S3.

The same shape as the terminal widget next door: connections are saved in the
vault, the password is only offered for saving once it is known to work, and
every call that touches the network happens on a thread and comes back through
a slot. A listing is a network round trip, and the desk cannot wait on it.

MinIO needs two things Amazon does not: an endpoint of its own, and paths that
look like /bucket/key rather than bucket.host/key. Both are set whenever an
endpoint is given, which is exactly when it is not Amazon.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..vault import Vault

# How many things to show from one listing. A bucket can hold millions; a
# widget can show a screenful, and asking for more costs time and money.
PAGE = 200
DOWNLOADS = Path.home() / "Downloads"


def _client(details: dict):
    """A boto3 S3 client for Amazon or for whatever else is on that endpoint."""
    import boto3
    from botocore.config import Config

    endpoint = str(details.get("endpoint") or "").strip()
    settings = {"signature_version": "s3v4", "retries": {"max_attempts": 2}}
    if endpoint:
        # Anything with its own endpoint is not Amazon, and almost everything
        # that is not Amazon wants the bucket in the path.
        settings["s3"] = {"addressing_style": "path"}
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        region_name=str(details.get("region") or "") or None,
        aws_access_key_id=str(details.get("access_key") or "") or None,
        aws_secret_access_key=str(details.get("secret_key") or "") or None,
        config=Config(connect_timeout=8, read_timeout=20, **settings),
    )


def list_entries(client, bucket: str, prefix: str) -> list[dict]:
    """One level of one bucket: the folders first, then the objects.

    S3 has no folders. A listing delimited by "/" invents them, which is what
    everybody means by a folder anyway.
    """
    if not bucket:
        answer = client.list_buckets()
        return [
            {"name": b["Name"], "kind": "bucket", "size": 0,
             "when": b.get("CreationDate").isoformat() if b.get("CreationDate") else ""}
            for b in answer.get("Buckets", [])
        ]

    answer = client.list_objects_v2(
        Bucket=bucket, Prefix=prefix, Delimiter="/", MaxKeys=PAGE
    )
    out = [
        {"name": p["Prefix"][len(prefix):].rstrip("/"), "kind": "folder", "size": 0, "when": ""}
        for p in answer.get("CommonPrefixes", [])
    ]
    for item in answer.get("Contents", []):
        name = item["Key"][len(prefix):]
        if not name:
            continue  # the folder marker itself
        out.append({
            "name": name, "kind": "object", "size": int(item.get("Size", 0)),
            "when": item["LastModified"].isoformat() if item.get("LastModified") else "",
        })
    return out


class _Browser:
    """Where one widget is looking, and what it found there."""

    def __init__(self, ident: str, provider: "Buckets"):
        self.ident = ident
        self._provider = provider
        self.state = "idle"
        self.message = ""
        self.bucket = ""
        self.prefix = ""
        self.entries: list[dict] = []
        self.details: dict = {}
        self.offer = False
        self.client = None

    # ---- what the widget asks for -----------------------------------------

    def connect(self, details: dict):
        self.details = dict(details)
        self.offer = False
        self.bucket, self.prefix = str(details.get("bucket") or ""), ""
        self._say("connecting", str(details.get("endpoint") or "Amazon S3"))
        self._work(self._connect)

    def go(self, bucket: str, prefix: str):
        self.bucket, self.prefix = bucket, prefix
        self.reload()

    def reload(self):
        if self.client is None:
            return
        self._say("loading", "")
        self._work(self._list)

    def download(self, name: str):
        if self.client is None or not self.bucket:
            return
        self._work(lambda: self._download(name))

    def close(self):
        self.client = None
        self.entries = []
        self._say("idle", "")

    # ---- the parts that wait on a network ---------------------------------

    def _work(self, job):
        threading.Thread(target=self._guard, args=(job,), daemon=True).start()

    def _guard(self, job):
        try:
            job()
        except Exception as e:
            self._say("failed", _plain(e))

    def _connect(self):
        client = _client(self.details)
        # Something that proves the keys work. Listing buckets is the usual
        # one; a key that may only touch its own bucket is allowed to fail it,
        # so that case falls back to listing inside the bucket it was given.
        try:
            client.list_buckets()
        except Exception:
            if not self.bucket:
                raise
            client.list_objects_v2(Bucket=self.bucket, MaxKeys=1)
        self.client = client
        self.offer = bool(self.details.get("secret_key") and not self.details.get("saved"))
        self._say("ready", "")
        self._list()

    def _list(self):
        self.entries = list_entries(self.client, self.bucket, self.prefix)
        self._say("ready", "" if self.entries else "nothing here")

    def _download(self, name: str):
        key = self.prefix + name
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        target = DOWNLOADS / Path(name).name
        # Never write over something already there.
        stem, suffix, n = target.stem, target.suffix, 2
        while target.exists():
            target = DOWNLOADS / f"{stem} ({n}){suffix}"
            n += 1
        self._say("loading", f"downloading {Path(name).name}...")
        self.client.download_file(self.bucket, key, str(target))
        self._say("ready", f"saved to {target.name}")
        self._provider.downloaded(self.ident, str(target))

    def _say(self, state: str, message: str):
        self.state, self.message = state, message
        self._provider.state_changed(self.ident)


def _plain(error: Exception) -> str:
    """The readable half of a boto error."""
    answer = getattr(error, "response", None)
    if isinstance(answer, dict):
        inner = answer.get("Error", {})
        code, message = inner.get("Code", ""), inner.get("Message", "")
        if code or message:
            return f"{code}: {message}".strip(": ")
    return str(error) or error.__class__.__name__


class Buckets(QObject):
    """Exposed to QML as `Buckets`: one browser per widget."""

    stateChanged = Signal(str)
    savedChanged = Signal()
    fileSaved = Signal(str, str)
    _state = Signal(str)
    _saved = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._browsers: dict[str, _Browser] = {}
        self._vault = Vault()
        # Signals from worker threads reach QML through slots, never by being
        # chained to another signal: that delivers on the emitting thread.
        self._state.connect(self._on_state)
        self._saved.connect(self._on_saved)

    def start(self):
        pass

    def stop(self):
        for browser in list(self._browsers.values()):
            browser.close()
        self._browsers.clear()

    # ---- from the threads -------------------------------------------------

    def state_changed(self, ident: str):
        self._state.emit(ident)

    def downloaded(self, ident: str, path: str):
        self._saved.emit(ident, path)

    @Slot(str)
    def _on_state(self, ident: str):
        self.stateChanged.emit(ident)

    @Slot(str, str)
    def _on_saved(self, ident: str, path: str):
        self.fileSaved.emit(ident, path)

    # ---- from QML ---------------------------------------------------------

    def _browser(self, ident: str) -> _Browser:
        browser = self._browsers.get(ident)
        if browser is None:
            browser = self._browsers[ident] = _Browser(ident, self)
        return browser

    @Slot(str, "QVariant")
    def open(self, ident: str, details):
        self._browser(ident).connect(dict(details or {}))

    @Slot(str, str)
    def openSaved(self, ident: str, name: str):
        entry = self._vault.find(name, "s3")
        if not entry:
            return
        details = {k: entry.get(k, "") for k in ("endpoint", "region", "bucket")}
        details.update(self._vault.secrets(name))
        details["name"] = name
        details["saved"] = True
        self.open(ident, details)

    @Slot(str)
    def close(self, ident: str):
        browser = self._browsers.pop(ident, None)
        if browser:
            browser.close()

    @Slot(str, str)
    def enter(self, ident: str, name: str):
        browser = self._browsers.get(ident)
        if not browser:
            return
        if not browser.bucket:
            browser.go(name, "")
        else:
            browser.go(browser.bucket, browser.prefix + name + "/")

    @Slot(str)
    def up(self, ident: str):
        browser = self._browsers.get(ident)
        if not browser:
            return
        if browser.prefix:
            parent = browser.prefix.rstrip("/").rpartition("/")[0]
            browser.go(browser.bucket, parent + "/" if parent else "")
        elif browser.bucket and not browser.details.get("bucket"):
            # Back to the list of buckets - unless this connection was pinned
            # to one bucket, in which case that is as far out as it goes.
            browser.go("", "")

    @Slot(str)
    def refresh(self, ident: str):
        browser = self._browsers.get(ident)
        if browser:
            browser.reload()

    @Slot(str, str)
    def download(self, ident: str, name: str):
        browser = self._browsers.get(ident)
        if browser:
            browser.download(name)

    @Slot(str, result="QVariantList")
    def entries(self, ident: str) -> list:
        browser = self._browsers.get(ident)
        return list(browser.entries) if browser else []

    @Slot(str, result=str)
    def state(self, ident: str) -> str:
        browser = self._browsers.get(ident)
        return browser.state if browser else "idle"

    @Slot(str, result=str)
    def message(self, ident: str) -> str:
        browser = self._browsers.get(ident)
        return browser.message if browser else ""

    @Slot(str, result=str)
    def where(self, ident: str) -> str:
        """The path being shown, for the widget's heading."""
        browser = self._browsers.get(ident)
        if not browser:
            return ""
        if not browser.bucket:
            return "Buckets"
        return browser.bucket + "/" + browser.prefix

    @Slot(str, result=bool)
    def canGoUp(self, ident: str) -> bool:
        browser = self._browsers.get(ident)
        if not browser:
            return False
        return bool(browser.prefix) or (bool(browser.bucket) and not browser.details.get("bucket"))

    # ---- saving a connection ----------------------------------------------

    @Slot(str, result=bool)
    def offersSave(self, ident: str) -> bool:
        browser = self._browsers.get(ident)
        return bool(browser and browser.offer)

    @Slot(str, result=str)
    def suggestedName(self, ident: str) -> str:
        browser = self._browsers.get(ident)
        if not browser:
            return ""
        details = browser.details
        endpoint = str(details.get("endpoint") or "")
        return str(details.get("name") or endpoint.split("//")[-1] or "Amazon S3")

    @Slot(str, str)
    def saveConnection(self, ident: str, name: str):
        browser = self._browsers.get(ident)
        if not browser:
            return
        details = browser.details
        self._vault.save(
            {
                "name": str(name or "S3"),
                "kind": "s3",
                "endpoint": details.get("endpoint", ""),
                "region": details.get("region", ""),
                "bucket": details.get("bucket", ""),
            },
            {
                "access_key": str(details.get("access_key") or ""),
                "secret_key": str(details.get("secret_key") or ""),
            },
        )
        browser.offer = False
        browser.details["saved"] = True
        self.savedChanged.emit()
        self.stateChanged.emit(ident)

    @Slot(str)
    def declineSave(self, ident: str):
        browser = self._browsers.get(ident)
        if browser:
            browser.offer = False
            self.stateChanged.emit(ident)

    @Property("QVariantList", notify=savedChanged)
    def saved(self) -> list:
        return self._vault.listing("s3")

    @Slot(str)
    def forget(self, name: str):
        self._vault.forget(name)
        self.savedChanged.emit()

    @Slot(str, result=str)
    def reveal(self, path: str) -> str:
        """Show a downloaded file in Explorer."""
        try:
            os.startfile(str(Path(path).parent))
        except OSError as e:
            return str(e)
        return ""
