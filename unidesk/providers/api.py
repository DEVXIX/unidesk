"""Send an HTTP request from the desk and look at what comes back.

A small API client: method, address, headers, body, send. Enough to check
whether something is up, what it answers and how long it took, without
opening a program to do it.

urllib rather than a library, because it is already here and this does not
need connection pooling or retries - one request, one answer. What it does
need is the machine's own certificate store, which truststore gives it, so
anything signed by a company CA works the way it does in a browser.

The same shape as the other providers: one of these holds every request
widget on the desk, keyed by the widget's id, and everything that waits on a
network happens on a thread and comes back through a slot.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from PySide6.QtCore import Property, QObject, Signal, Slot

from .. import __version__
from ..config import from_qml
from ..vault import Vault

# Past this, a request is not going to answer in a way anybody is waiting for.
TIMEOUT = 30
# A response bigger than this is not going in a widget; enough of it is.
MOST = 400_000
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
# What this calls itself on the wire.
#
# urllib says "Python-urllib/3.12" if nobody tells it otherwise, and a great
# many sites refuse that outright - Cloudflare answers it with 403 and error
# code 1010, which says nothing about the request and everything about who
# asked. Saying who we actually are is enough; there is no need to pretend to
# be a browser, and anything typed in the Headers box still wins.
AGENT = f"unidesk/{__version__}"


def parse_headers(text: str) -> list[tuple[str, str]]:
    """"Name: value" a line, the way every tool writes them.

    Blank lines and anything starting with # are skipped, so a header can be
    commented out without deleting it.
    """
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition(":")
        if sep and name.strip():
            out.append((name.strip(), value.strip()))
    return out


def prettify(body: bytes, content_type: str) -> tuple[str, str]:
    """The body as text, and what kind of thing it turned out to be.

    JSON is laid out rather than left in one line, because a response on one
    line is the thing every API client exists to avoid.
    """
    text = body.decode("utf-8", "replace")
    kind = content_type.split(";")[0].strip().lower()
    looks_json = "json" in kind or text[:1] in ("{", "[")
    if looks_json:
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False), "json"
        except ValueError:
            pass
    return text, "text" if kind.startswith("text/") or not kind else kind


def readable(size: int) -> str:
    units = ["B", "KB", "MB"]
    n, i = float(size), 0
    while n >= 1024 and i < len(units) - 1:
        n, i = n / 1024, i + 1
    return f"{int(n)} {units[i]}" if i == 0 else f"{n:.1f} {units[i]}"


def auth_headers(auth: dict) -> list[tuple[str, str]]:
    """The one header an authentication scheme comes down to.

    All three of these are a header in the end; the widget asks the question
    in the shape people think about it (a token, a username and password, a
    key) and this turns the answer into what goes on the wire.
    """
    kind = str(auth.get("type") or "none").lower()
    if kind == "bearer":
        token = str(auth.get("token") or "").strip()
        return [("Authorization", f"Bearer {token}")] if token else []
    if kind == "basic":
        import base64

        user, password = str(auth.get("user") or ""), str(auth.get("password") or "")
        if not user and not password:
            return []
        pair = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        return [("Authorization", f"Basic {pair}")]
    if kind == "key":
        name = str(auth.get("key_name") or "").strip()
        value = str(auth.get("key_value") or "")
        return [(name, value)] if name else []
    return []


def make_body(body: str, kind: str) -> tuple[bytes | None, str]:
    """The bytes to send and the type to call them.

    A form is written the way headers are - one `name=value` a line - because
    a widget with a table in it is a widget nobody can read.
    """
    kind = (kind or "auto").lower()
    if kind == "none" or not body.strip():
        return None, ""
    if kind == "auto":
        # Nobody said, so the body itself decides. Anything else would mean a
        # body quietly not being sent, which is worse than guessing wrong.
        kind = "json" if body.lstrip()[:1] in ("{", "[") else "text"
    if kind == "form":
        from urllib.parse import urlencode

        pairs = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if sep:
                pairs.append((name.strip(), value.strip()))
        return urlencode(pairs).encode("utf-8"), "application/x-www-form-urlencoded"
    if kind == "json":
        return body.encode("utf-8"), "application/json"
    return body.encode("utf-8"), "text/plain; charset=utf-8"


def send_request(request: dict) -> dict:
    """One request, one answer. Never raises: a failure is an answer too."""
    url = str(request.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "no address"}
    if "://" not in url:
        url = "https://" + url
    method = str(request.get("method") or "GET").upper()
    if method not in METHODS:
        method = "GET"

    body = str(request.get("body") or "")
    data, content_type = (None, "")
    if method not in ("GET", "HEAD"):
        data, content_type = make_body(body, str(request.get("body_type") or "auto"))

    headers = parse_headers(request.get("headers"))
    auth = request.get("auth")
    headers += auth_headers(auth if isinstance(auth, dict) else {})
    names = {name.lower() for name, _ in headers}
    # A header typed by hand wins: it is the more deliberate of the two.
    if data is not None and content_type and "content-type" not in names:
        headers.append(("Content-Type", content_type))
    if "user-agent" not in names:
        headers.append(("User-Agent", AGENT))

    prepared = urllib.request.Request(url, data=data, method=method)
    for name, value in headers:
        prepared.add_header(name, value)

    started = time.monotonic()
    try:
        with urllib.request.urlopen(prepared, timeout=TIMEOUT) as answer:
            raw, status, reason = answer.read(MOST + 1), answer.status, answer.reason
            got = dict(answer.headers)
    except urllib.error.HTTPError as e:
        # Not a failure: a 404 is an answer, and its body usually says why.
        raw, status, reason, got = e.read(MOST + 1), e.code, e.reason, dict(e.headers or {})
    except Exception as e:
        return {"ok": False, "error": str(e) or e.__class__.__name__,
                "ms": int((time.monotonic() - started) * 1000)}

    ms = int((time.monotonic() - started) * 1000)
    clipped = len(raw) > MOST
    text, kind = prettify(raw[:MOST], got.get("Content-Type", ""))
    if clipped:
        text += "\n\n... the rest is not shown"
    return {
        "ok": True, "status": int(status), "reason": str(reason or ""), "ms": ms,
        "size": readable(len(raw)), "body": text, "kind": kind,
        "headers": "\n".join(f"{name}: {value}" for name, value in got.items()),
        "host": urlsplit(url).netloc,
    }


class Api(QObject):
    """Exposed to QML as `Api`: one request in flight per widget."""

    changed = Signal(str)
    savedChanged = Signal()
    _done = Signal(str, "QVariant")

    def __init__(self):
        super().__init__()
        self._answers: dict[str, dict] = {}
        self._busy: set[str] = set()
        self._vault = Vault()
        # Through a slot, never signal to signal: the worker's thread is not
        # the one the widgets live on.
        self._done.connect(self._on_done)

    def start(self):
        pass

    def stop(self):
        self._answers.clear()
        self._busy.clear()

    @Slot(str, "QVariantMap")
    def send(self, ident: str, request):
        """Send what the widget has in its boxes."""
        request = from_qml(request)
        if not isinstance(request, dict):
            return
        if ident in self._busy:
            return
        self._busy.add(ident)
        self._answers.pop(ident, None)
        self.changed.emit(ident)

        def work():
            self._done.emit(ident, send_request(request))

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, "QVariant")
    def _on_done(self, ident: str, answer):
        self._busy.discard(ident)
        self._answers[ident] = dict(answer)
        self.changed.emit(ident)

    # ---- what QML reads ---------------------------------------------------

    @Slot(str, result=bool)
    def busy(self, ident: str) -> bool:
        return ident in self._busy

    @Slot(str, result="QVariantMap")
    def answer(self, ident: str) -> dict:
        return dict(self._answers.get(ident) or {})

    @Slot(str, result=bool)
    def copy(self, text: str) -> bool:
        """Put a response on the clipboard, plainly.

        Not TextEdit's own copy(): that offers the clipboard three formats at
        once (plain, HTML, OpenDocument) and Windows refuses the whole thing
        if anything else has the clipboard open for that instant - which it
        regularly does. Plain text and a second try is what actually lands.
        """
        from PySide6.QtGui import QGuiApplication

        board = QGuiApplication.clipboard()
        if board is None:
            return False
        for attempt in range(6):
            board.setText(text)
            if board.text() == text:
                return True
            time.sleep(0.03)
        print("[unidesk] the clipboard would not take the response")
        return False

    @Slot(result="QVariantList")
    def methods(self) -> list:
        return list(METHODS)

    # ---- saved requests ---------------------------------------------------
    #
    # The address and method are plain, because a list you cannot read is not
    # a list. Headers and body are not: an Authorization header is a password
    # in all but name, and people paste them into these boxes all day.

    @Slot(str, "QVariantMap")
    def remember(self, name: str, request):
        request = from_qml(request)
        if not isinstance(request, dict):
            return
        auth = request.get("auth") if isinstance(request.get("auth"), dict) else {}
        self._vault.save(
            {"name": str(name or request.get("url") or "request"), "kind": "http",
             "method": str(request.get("method") or "GET"),
             "url": str(request.get("url") or ""),
             "body_type": str(request.get("body_type") or "none"),
             "auth_type": str(auth.get("type") or "none")},
            {"headers": str(request.get("headers") or ""),
             "body": str(request.get("body") or ""),
             "token": str(auth.get("token") or ""),
             "user": str(auth.get("user") or ""),
             "password": str(auth.get("password") or ""),
             "key_name": str(auth.get("key_name") or ""),
             "key_value": str(auth.get("key_value") or "")},
        )
        self.savedChanged.emit()

    # ---- what a widget is in the middle of --------------------------------
    #
    # Kept in the vault rather than in the widget's options, because a config
    # file is the thing people paste into an issue and this holds a bearer
    # token, a password, and whatever was in the headers box.

    @Slot(str, "QVariantMap")
    def keepDraft(self, ident: str, request):
        request = from_qml(request)
        if not isinstance(request, dict) or not ident:
            return
        plain = {"name": f"draft:{ident}", "kind": "http-draft",
                 "method": str(request.get("method") or "GET"),
                 "url": str(request.get("url") or ""),
                 "body_type": str(request.get("body_type") or "none"),
                 "auth_type": str((request.get("auth") or {}).get("type") or "none")}
        auth = request.get("auth") if isinstance(request.get("auth"), dict) else {}
        self._vault.save(plain, {
            "headers": str(request.get("headers") or ""),
            "body": str(request.get("body") or ""),
            "token": str(auth.get("token") or ""),
            "user": str(auth.get("user") or ""),
            "password": str(auth.get("password") or ""),
            "key_name": str(auth.get("key_name") or ""),
            "key_value": str(auth.get("key_value") or ""),
        })

    @Slot(str, result="QVariantMap")
    def draft(self, ident: str) -> dict:
        name = f"draft:{ident}"
        entry = self._vault.find(name, "http-draft")
        if not entry:
            return {}
        out = {k: entry.get(k, "") for k in ("method", "url", "body_type", "auth_type")}
        out.update(self._vault.secrets(name))
        return out

    @Slot(str, result="QVariantMap")
    def recall(self, name: str) -> dict:
        entry = self._vault.find(name, "http")
        if not entry:
            return {}
        out = {"name": name, "method": entry.get("method", "GET"), "url": entry.get("url", ""),
               "body_type": entry.get("body_type", "none"), "auth_type": entry.get("auth_type", "none")}
        out.update(self._vault.secrets(name))
        return out

    @Slot(str)
    def forget(self, name: str):
        self._vault.forget(name)
        self.savedChanged.emit()

    @Property("QVariantList", notify=savedChanged)
    def saved(self) -> list:
        return self._vault.listing("http")
