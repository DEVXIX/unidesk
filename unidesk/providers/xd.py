"""xD (eksde.app): your messages, your notifications and today's word.

One provider serves every xD widget, because they share the thing that is
awkward: a session. Signing in once fills a token that all of them use, and a
401 anywhere clears it so the widgets ask again rather than each quietly
failing on its own.

The token is kept out of config.yaml, in a file of its own with no comments and
no round-tripping, because config.yaml is the file people copy to a friend to
share their setup - a password manager is not what it is for.

Everything network happens on a worker thread and lands back through signals;
nothing here blocks the desk. Polling is deliberate rather than the Reverb
socket the website uses: a widget that is right within a few seconds costs one
small request, and a WebSocket that must be reconnected, resubscribed and
re-authenticated is a great deal of machinery for the same picture.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .net import get_json, send_json

API = "https://admin.eksde.app"
SITE = "https://eksde.app"
_STORE = Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk" / "xd-session.json"


def _read_session() -> dict:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_session(data: dict) -> None:
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(json.dumps(data), encoding="utf-8")
    except OSError as e:
        print(f"[unidesk] xD: could not save the session: {e}")


class XD(QObject):
    """Exposed to QML as `XD`. One session, several widgets."""

    changed = Signal()
    busyChanged = Signal()
    errorChanged = Signal()
    messagesChanged = Signal()
    threadChanged = Signal()
    wordleChanged = Signal()
    sectionChanged = Signal()

    def __init__(self):
        super().__init__()
        session = _read_session()
        self._token: str = str(session.get("token") or "")
        self._me: str = str(session.get("user") or "")
        self._busy = False
        self._error = ""
        self._conversations: list = []
        self._notifications: list = []
        self._unread = 0
        self._badge = 0
        self._thread: list = []
        self._thread_with = ""
        self._wordle: dict = {}
        self._section: list = []
        # Slow enough to be polite to somebody else's server, quick enough that
        # a message feels like it arrived rather than was fetched.
        self._poll = QTimer(self, interval=20_000, timeout=self.refresh)
        if self._token:
            self._poll.start()
            QTimer.singleShot(1200, self.refresh)

    # ---- lifecycle ---------------------------------------------------------------
    # The desk starts a provider when a widget needs it and stops it when the
    # last one goes, so polling only runs while something is on screen to show
    # it. Signing in is not undone by stopping: the session outlives the widget.

    @Slot()
    def start(self):
        if self._token and not self._poll.isActive():
            self._poll.start()
            QTimer.singleShot(400, self.refresh)

    @Slot()
    def stop(self):
        self._poll.stop()

    # ---- plumbing ----------------------------------------------------------------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _set_error(self, message: str):
        if message != self._error:
            self._error = message
            self.errorChanged.emit()

    def _set_busy(self, on: bool):
        if on != self._busy:
            self._busy = on
            self.busyChanged.emit()

    def _forget(self):
        """A 401 anywhere means the session is done; say so once, everywhere."""
        self._token = ""
        self._me = ""
        self._poll.stop()
        _write_session({})
        self._set_error("Signed out of xD. Sign in again.")
        self.changed.emit()

    def _work(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # ---- session -----------------------------------------------------------------

    @Property(bool, notify=changed)
    def signedIn(self):
        return bool(self._token)

    @Property(str, notify=changed)
    def me(self):
        return self._me

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    @Slot(str, str)
    def signIn(self, username: str, password: str):
        username, password = str(username).strip(), str(password)
        if not username or not password:
            self._set_error("Enter your xD username and password.")
            return
        self._set_busy(True)
        self._set_error("")

        def run():
            try:
                status, body = send_json(f"{API}/v1/login", {"username": username, "password": password})
            except Exception as e:
                QTimer.singleShot(0, lambda: (self._set_busy(False), self._set_error(f"xD is not reachable: {e}")))
                return

            def done():
                self._set_busy(False)
                if status == 401 or status == 422:
                    self._set_error("That username and password were refused.")
                    return
                token = (body or {}).get("token") if isinstance(body, dict) else None
                if status >= 400 or not token:
                    self._set_error(f"xD refused the sign in (HTTP {status}).")
                    return
                self._token = str(token)
                self._me = str((body or {}).get("user") or username)
                _write_session({"token": self._token, "user": self._me})
                self._set_error("")
                self.changed.emit()
                self._poll.start()
                self.refresh()

            QTimer.singleShot(0, done)

        self._work(run)

    @Slot()
    def signOut(self):
        token = self._token
        self._forget()
        if token:
            self._work(lambda: send_json(f"{API}/v1/logout", {}, {"Authorization": f"Bearer {token}"}))

    # ---- what the widgets show ---------------------------------------------------

    @Property("QVariantList", notify=messagesChanged)
    def conversations(self):
        return self._conversations

    @Property("QVariantList", notify=threadChanged)
    def thread(self):
        return self._thread

    @Property(str, notify=threadChanged)
    def threadWith(self):
        return self._thread_with

    @Property("QVariantList", notify=changed)
    def notifications(self):
        return self._notifications

    @Property(int, notify=messagesChanged)
    def unread(self):
        return self._unread

    @Property(int, notify=changed)
    def badge(self):
        return self._badge

    @Property("QVariantMap", notify=wordleChanged)
    def wordle(self):
        return self._wordle

    @Property("QVariantList", notify=sectionChanged)
    def section(self):
        """Whatever the open section holds. One list, because the timeline, the
        quests and the rooms are all a line of text with a name under it, and
        one shape means one delegate rather than four that drift apart."""
        return self._section

    @Slot(str)
    def loadSection(self, name: str):
        route = {"tweets": "tweets", "quests": "quests", "rooms": "rooms"}.get(str(name))
        if not route or not self._token:
            return
        self._set_busy(True)

        def run():
            try:
                body = get_json(f"{API}/v1/{route}", self._headers())
            except Exception:
                body = None
            QTimer.singleShot(0, lambda: self._set_section(_as_list(body)))

        self._work(run)

    def _set_section(self, items: list):
        self._set_busy(False)
        self._section = items
        self.sectionChanged.emit()

    @Slot()
    def refresh(self):
        """Everything the widgets show, in one pass on one thread."""
        if not self._token:
            return

        def run():
            headers = self._headers()
            out: dict = {}
            unauthorised = False
            for key, url in (
                ("conversations", f"{API}/v1/messages"),
                ("notifications", f"{API}/v1/notifications"),
                ("unread", f"{API}/v1/messages/unread-count"),
                ("badge", f"{API}/v1/badge-count"),
            ):
                try:
                    out[key] = get_json(url, headers)
                except Exception as e:
                    if "401" in str(e):
                        unauthorised = True
                        break

            def done():
                if unauthorised:
                    self._forget()
                    return
                if "conversations" in out:
                    self._conversations = _as_list(out["conversations"])
                    self.messagesChanged.emit()
                if "notifications" in out:
                    self._notifications = _as_list(out["notifications"])
                if "unread" in out:
                    self._unread = _as_count(out["unread"])
                    self.messagesChanged.emit()
                if "badge" in out:
                    self._badge = _as_count(out["badge"])
                self.changed.emit()

            QTimer.singleShot(0, done)

        self._work(run)

    @Slot(str)
    def openThread(self, handle: str):
        """The conversation with one person, newest last."""
        handle = str(handle).strip()
        if not handle or not self._token:
            return
        self._thread_with = handle
        self.threadChanged.emit()

        def run():
            try:
                body = get_json(f"{API}/v1/messages/{handle}", self._headers())
            except Exception:
                body = None
            QTimer.singleShot(0, lambda: self._set_thread(_as_list(body)))

        self._work(run)

    def _set_thread(self, items: list):
        self._thread = items
        self.threadChanged.emit()

    @Slot(str, str)
    def send(self, handle: str, text: str):
        handle, text = str(handle).strip(), str(text).strip()
        if not handle or not text or not self._token:
            return
        headers = self._headers()

        def run():
            try:
                send_json(f"{API}/v1/messages", {"username": handle, "content": text}, headers)
            except Exception as e:
                QTimer.singleShot(0, lambda: self._set_error(f"xD would not take that message: {e}"))
                return
            QTimer.singleShot(0, lambda: (self.openThread(handle), self.refresh()))

        self._work(run)

    # ---- today's word ------------------------------------------------------------

    @Slot()
    def loadWordle(self):
        if not self._token:
            return

        def run():
            try:
                today = get_json(f"{API}/v1/wordle/today", self._headers())
                stats = get_json(f"{API}/v1/wordle/stats", self._headers())
            except Exception:
                return
            QTimer.singleShot(0, lambda: self._set_wordle(today, stats))

        self._work(run)

    def _set_wordle(self, today, stats):
        self._wordle = {
            "today": today if isinstance(today, dict) else {},
            "stats": stats if isinstance(stats, dict) else {},
        }
        self.wordleChanged.emit()

    @Slot(str)
    def guess(self, word: str):
        word = str(word).strip().lower()
        if len(word) < 3 or not self._token:
            return
        headers = self._headers()

        def run():
            try:
                send_json(f"{API}/v1/wordle/guess", {"guess": word}, headers)
            except Exception:
                pass
            QTimer.singleShot(0, self.loadWordle)

        self._work(run)

    @Slot(str)
    def open(self, where: str):
        """Hand something to the website, for anything a widget should not do."""
        import webbrowser

        path = str(where or "").lstrip("/")
        webbrowser.open(f"{SITE}/{path}" if path else SITE)


def _as_list(value) -> list:
    """The API answers either a bare list or {data: [...]}; both are fine."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "messages", "conversations", "notifications"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _as_count(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        for key in ("count", "unread", "unread_count", "total", "badge"):
            if isinstance(value.get(key), (int, float)):
                return int(value[key])
    return 0
