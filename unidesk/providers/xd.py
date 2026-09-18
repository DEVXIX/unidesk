"""xD (eksde.app): messages, notifications, the timeline, quests and a word game.

One provider serves the whole xD widget, because what its sections share is the
awkward part: a session. Signing in once fills a token they all use, and a 401
anywhere clears it so the widget asks again rather than each section quietly
failing on its own.

The token is kept out of config.yaml, in a file of its own, because config.yaml
is what you hand a friend to share your setup and a password is not part of it.

Every request runs on a worker thread and comes back through `_result`, which
is a signal rather than a callback. That matters more than it looks: a QTimer
started on a worker thread belongs to a thread with no event loop and simply
never fires, so anything waiting on it waits for ever - which is exactly how
"Signing in..." became a state you could not leave. A queued signal is what
actually crosses back to the thread Qt draws on.

Polling rather than the Reverb socket the website uses: being right within
twenty seconds costs one small request, where a socket that must be
reconnected, resubscribed and re-authenticated is a great deal of machinery for
the same picture.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .net import get_json, send_json

# The spec writes its paths as /v1/..., but the server mounts them under /api,
# which is what the website itself calls (lib/api.ts: API_BASE = "/api/v1").
# Without the prefix every request is a 404 and the widget looks broken.
API = "https://admin.eksde.app/api"
SITE = "https://eksde.app"
_STORE = Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk" / "xd-session.json"
# Long enough to be patient, short enough that a server which stopped answering
# does not leave the widget saying "Signing in..." until somebody gives up.
TIMEOUT = 12.0

# The games xD hosts, by the slug its own pages use. There is no endpoint that
# lists them - /v1/games is a 404, the routes are all /v1/games/<slug>/... - so
# the list lives here, taken from the website's own pages.
DAILY_GAMES = [("wordle", "Wordle"), ("sudoku", "Sudoku"), ("crossword", "Crossword"), ("zip", "Zip")]
ARCADE_GAMES = [
    ("aqua-grabber", "Aqua Grabber"), ("astro-barrier", "Astro Barrier"),
    ("balloon-pop", "Balloon Pop"), ("bean-counters", "Bean Counters"),
    ("cart-surfer", "Cart Surfer"), ("catchin-waves", "Catchin' Waves"),
    ("dance-contest", "Dance Contest"), ("dj3k", "DJ3K"),
    ("feed-a-puffle", "Feed a Puffle"), ("fluffy-the-fish", "Fluffy the Fish"),
    ("hydro-hopper", "Hydro Hopper"), ("ice-fishing", "Ice Fishing"),
    ("jetpack-adventure", "Jetpack Adventure"), ("pizzatron", "Pizzatron"),
    ("puffle-launch", "Puffle Launch"), ("puffle-paddle", "Puffle Paddle"),
    ("puffle-rescue", "Puffle Rescue"), ("puffle-roundup", "Puffle Roundup"),
    ("puffle-soaker", "Puffle Soaker"),
]


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


# Some pictures come back as a full address and some as a path inside the
# bucket. A relative one handed to Qt is resolved against the QML file and
# quietly fails to load, so they are all made absolute here.
MEDIA_BASE = "https://eksde.app/s3/xd-uploads/"


def _media(url) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return MEDIA_BASE + text.lstrip("/")


def _as_list(value) -> list:
    """The API answers either a bare list or {data: [...]}; both are fine."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "messages", "conversations", "notifications",
                    "tweets", "rooms", "quests", "results"):
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


def _ids(items) -> list:
    """What a list is, for telling "the same again" from "something new"."""
    return [x.get("id") for x in items if isinstance(x, dict)]


def _with_media(items: list) -> list:
    """Absolute addresses for anything a tweet will try to draw."""
    for row in items:
        if not isinstance(row, dict):
            continue
        author = row.get("author")
        if isinstance(author, dict) and author.get("profile_picture"):
            author["profile_picture"] = _media(author["profile_picture"])
        media = row.get("media_urls")
        if isinstance(media, list):
            for m in media:
                if isinstance(m, dict) and m.get("url"):
                    m["url"] = _media(m["url"])
    return items


class XD(QObject):
    """Exposed to QML as `XD`. One session, one widget, several sections."""

    changed = Signal()
    busyChanged = Signal()
    errorChanged = Signal()
    messagesChanged = Signal()
    threadChanged = Signal()
    wordleChanged = Signal()
    sectionChanged = Signal()
    # Raised once a tweet is actually on the timeline, so the box can clear.
    posted = Signal()
    # Worker thread -> here. Qt makes this a queued connection across threads,
    # which is the whole point: nothing below touches state off the GUI thread.
    _result = Signal(str, "QVariant")

    def __init__(self):
        super().__init__()
        session = _read_session()
        self._token: str = str(session.get("token") or "")
        self._me: str = str(session.get("user") or "")
        self._busy = False
        self._error = ""
        self._conversations: list = []
        self._notifications: list = []
        self._section: list = []
        self._thread: list = []
        self._thread_with = ""
        self._open_section = ""
        self._wordle: dict = {}
        self._unread = 0
        self._badge = 0
        self._me_id = int(session.get('id') or 0)
        self._avatar = str(session.get('avatar') or '')
        self._result.connect(self._on_result)
        self._poll = QTimer(self, interval=20_000, timeout=self.refresh)
        if self._token:
            self._poll.start()
            QTimer.singleShot(1200, self.refresh)

    # ---- lifecycle ---------------------------------------------------------------

    @Slot()
    def start(self):
        """A widget that needs xD appeared."""
        if self._token and not self._poll.isActive():
            self._poll.start()
            QTimer.singleShot(400, self.refresh)

    @Slot()
    def stop(self):
        """Nothing is showing xD, so stop asking. The session stays."""
        self._poll.stop()

    # ---- plumbing ----------------------------------------------------------------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _work(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _set_busy(self, on: bool):
        if on != self._busy:
            self._busy = on
            self.busyChanged.emit()

    def _set_error(self, message: str):
        if message != self._error:
            self._error = message
            self.errorChanged.emit()

    def _forget(self):
        """A 401 anywhere means the session is over; say so once, everywhere."""
        self._token = ""
        self._me = ""
        self._poll.stop()
        _write_session({})
        self._set_busy(False)
        self._set_error("Signed out of xD. Sign in again.")
        self.changed.emit()

    @Slot(str, "QVariant")
    def _on_result(self, kind: str, payload):
        """Everything a worker thread came back with, on the GUI thread."""
        data = payload if isinstance(payload, dict) else {}
        self._set_busy(False)

        if kind == "login":
            if data.get("error"):
                self._set_error(str(data["error"]))
                return
            self._token = str(data.get("token") or "")
            self._me = str(data.get("user") or "")
            _write_session({"token": self._token, "user": self._me})
            self._set_error("")
            self.changed.emit()
            self._poll.start()
            self.refresh()

        elif kind == "unauthorised":
            self._forget()

        elif kind == "refresh":
            if data.get("me_id"):
                self._me_id = int(data["me_id"])
                self._avatar = str(data.get("avatar") or "")
            if "conversations" in data:
                self._conversations = self._conversations_from(data["conversations"])
            if "notifications" in data:
                self._notifications = data["notifications"]
            if "unread" in data:
                self._unread = data["unread"]
            if "badge" in data:
                self._badge = data["badge"]
            # Only when something actually arrived: replacing an identical model
            # resets the ListView, and a timeline that jumps to the top every
            # twenty seconds while you are reading it is worse than a stale one.
            if "section" in data:
                fresh = _with_media(data["section"])
                if _ids(fresh) != _ids(self._section):
                    self._section = fresh
                    self.sectionChanged.emit()
            if "thread" in data:
                if _ids(data["thread"]) != _ids(self._thread):
                    self._thread = data["thread"]
                    self.threadChanged.emit()
            self.messagesChanged.emit()
            self.changed.emit()

        elif kind == "thread":
            self._thread = data.get("items") or []
            self.threadChanged.emit()

        elif kind == "section":
            self._section = _with_media(data.get("items") or [])
            self.sectionChanged.emit()

        elif kind == "posted":
            self._section = _with_media(data.get("items") or [])
            self._set_error("")
            self.sectionChanged.emit()
            self.posted.emit()

        elif kind == "wordle":
            self._wordle = {"today": data.get("today") or {}, "stats": data.get("stats") or {}}
            self.wordleChanged.emit()

        elif kind == "error":
            self._set_error(str(data.get("message") or "xD did not answer."))

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
                status, body = send_json(
                    f"{API}/v1/login", {"username": username, "password": password}, timeout=TIMEOUT
                )
            except Exception as e:
                self._result.emit("login", {"error": f"xD is not reachable: {e}"})
                return
            token = body.get("token") if isinstance(body, dict) else None
            if status in (401, 403, 422):
                self._result.emit("login", {"error": "That username and password were refused."})
            elif status >= 400 or not token:
                self._result.emit("login", {"error": f"xD refused the sign in (HTTP {status})."})
            else:
                # `user` is sometimes the handle and sometimes the whole account;
                # what the widget needs either way is the name to compare against.
                user = body.get("user") if isinstance(body, dict) else None
                if isinstance(user, dict):
                    user = user.get("username") or user.get("handle") or user.get("name")
                self._result.emit("login", {"token": token, "user": user or username})

        self._work(run)

    @Slot()
    def signOut(self):
        token = self._token
        self._forget()
        if token:
            self._work(
                lambda: send_json(f"{API}/v1/logout", {}, {"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
            )

    # ---- what the widget shows ---------------------------------------------------

    @Property("QVariantList", notify=messagesChanged)
    def conversations(self):
        return self._conversations

    @Property("QVariantList", notify=threadChanged)
    def thread(self):
        return self._thread

    @Property("QVariantList", notify=changed)
    def notifications(self):
        return self._notifications

    @Property("QVariantList", notify=sectionChanged)
    def section(self):
        """Whatever the open section holds. The timeline, the quests and the
        rooms are all a line of text with a name under it, so they share one
        list rather than three that drift apart."""
        return self._section

    @Property(int, notify=messagesChanged)
    def unread(self):
        return self._unread

    @Property(int, notify=changed)
    def badge(self):
        return self._badge

    @Property("QVariantMap", notify=wordleChanged)
    def wordle(self):
        return self._wordle

    @Property("QVariantList", notify=changed)
    def games(self):
        """Every game, daily ones first. Playing one is the website's job - the
        widget has no browser in it - so each row carries the slug to open."""
        out = []
        for slug, name in DAILY_GAMES:
            out.append({"slug": slug, "name": name, "daily": True})
        for slug, name in ARCADE_GAMES:
            out.append({"slug": slug, "name": name, "daily": False})
        return out

    def _conversations_from(self, messages: list) -> list:
        """/v1/messages is every message, not a list of chats, so the chats are
        made here: newest message per person, with their name and picture off
        the sender or receiver, whichever is not me."""
        me = self._me_id
        chats: dict = {}
        for m in messages:
            if not isinstance(m, dict):
                continue
            sender, receiver = m.get("sender") or {}, m.get("receiver") or {}
            other = receiver if (me and m.get("sender_id") == me) else sender
            if not isinstance(other, dict) or not other.get("username"):
                continue
            handle = str(other.get("username"))
            row = chats.get(handle)
            when = str(m.get("created_at") or "")
            if row is None or when > row["at"]:
                chats[handle] = {
                    "handle": handle,
                    "name": str(other.get("display_name") or handle),
                    "avatar": _media(other.get("profile_picture")),
                    "last": str(m.get("content") or ("photo" if m.get("media_url") else "")),
                    "at": when,
                    "unread": 0,
                }
            if not m.get("is_read") and m.get("sender_id") != me:
                chats[handle]["unread"] = chats[handle].get("unread", 0) + 1
        return sorted(chats.values(), key=lambda c: c["at"], reverse=True)

    @Slot(str)
    def viewing(self, name: str):
        """What the widget is showing, so the poll can keep it current.

        Without this the timeline was whatever it was the moment you opened it,
        for as long as you left it open.
        """
        self._open_section = str(name or "")

    @Slot()
    def closeThread(self):
        self._thread_with = ""

    @Slot()
    def refresh(self):
        if not self._token:
            return
        headers = self._headers()
        # Read once here: the worker must not touch attributes the GUI thread
        # is free to change under it.
        open_section = self._open_section
        thread_with = self._thread_with

        def run():
            out: dict = {}
            if not self._me_id:
                try:
                    me = get_json(f"{API}/v1/me", headers, timeout=TIMEOUT)
                    if isinstance(me, dict):
                        out["me_id"] = me.get("id")
                        out["avatar"] = _media(me.get("profile_picture"))
                except Exception:
                    pass
            for key, url in (
                ("conversations", f"{API}/v1/messages"),
                ("notifications", f"{API}/v1/notifications"),
                ("unread", f"{API}/v1/messages/unread-count"),
                ("badge", f"{API}/v1/badge-count"),
            ):
                try:
                    body = get_json(url, headers, timeout=TIMEOUT)
                except Exception as e:
                    if "401" in str(e):
                        self._result.emit("unauthorised", {})
                        return
                    continue
                out[key] = _as_count(body) if key in ("unread", "badge") else _as_list(body)
            if open_section in ("tweets", "rooms"):
                try:
                    out["section"] = _as_list(
                        get_json(f"{API}/v1/{open_section}", headers, timeout=TIMEOUT)
                    )
                except Exception:
                    pass
            if thread_with:
                try:
                    out["thread"] = _as_list(
                        get_json(f"{API}/v1/messages/{thread_with}", headers, timeout=TIMEOUT)
                    )
                except Exception:
                    pass
            self._result.emit("refresh", out)

        self._work(run)

    @Slot(str)
    def openThread(self, handle: str):
        handle = str(handle).strip()
        if not handle or not self._token:
            return
        self._thread_with = handle
        self._set_busy(True)
        headers = self._headers()

        def run():
            try:
                body = get_json(f"{API}/v1/messages/{handle}", headers, timeout=TIMEOUT)
            except Exception:
                body = None
            self._result.emit("thread", {"items": _as_list(body)})

        self._work(run)

    @Slot(str, str)
    def send(self, handle: str, text: str):
        handle, text = str(handle).strip(), str(text).strip()
        if not handle or not text or not self._token:
            return
        headers = self._headers()

        def run():
            try:
                send_json(f"{API}/v1/messages", {"username": handle, "content": text}, headers, timeout=TIMEOUT)
            except Exception as e:
                self._result.emit("error", {"message": f"xD would not take that message: {e}"})
                return
            try:
                body = get_json(f"{API}/v1/messages/{handle}", headers, timeout=TIMEOUT)
            except Exception:
                body = None
            self._result.emit("thread", {"items": _as_list(body)})

        self._work(run)

    @Slot(str)
    def post(self, text: str):
        """Write a tweet. Text only - pictures are a file picker's job, not a widget's."""
        text = str(text).strip()
        if not text or not self._token:
            return
        self._set_busy(True)
        headers = self._headers()

        def run():
            try:
                status, body = send_json(
                    f"{API}/v1/tweets", {"content": text}, headers, timeout=TIMEOUT
                )
            except Exception as e:
                self._result.emit("error", {"message": f"xD would not take that: {e}"})
                return
            if status == 401:
                self._result.emit("unauthorised", {})
                return
            if status >= 400:
                # 422 carries the sentence explaining what was wrong with it.
                said = body.get("message") if isinstance(body, dict) else None
                self._result.emit("error", {"message": str(said or f"xD said no ({status}).")})
                return
            # Show the timeline it just landed on rather than only saying "sent".
            try:
                fresh = get_json(f"{API}/v1/tweets", headers, timeout=TIMEOUT)
            except Exception:
                fresh = None
            self._result.emit("posted", {"items": _as_list(fresh)})

        self._work(run)

    @Slot(str)
    def loadSection(self, name: str):
        # /v1/quests and /v1/games are 404s; only these two answer a plain list.
        route = {"tweets": "tweets", "rooms": "rooms"}.get(str(name))
        if not route or not self._token:
            return
        self._set_busy(True)
        headers = self._headers()

        def run():
            try:
                body = get_json(f"{API}/v1/{route}", headers, timeout=TIMEOUT)
            except Exception:
                body = None
            self._result.emit("section", {"items": _as_list(body)})

        self._work(run)

    # ---- today's word ------------------------------------------------------------

    def _wordle_now(self, headers: dict) -> dict:
        today = stats = None
        try:
            today = get_json(f"{API}/v1/wordle/today", headers, timeout=TIMEOUT)
        except Exception:
            pass
        try:
            stats = get_json(f"{API}/v1/wordle/stats", headers, timeout=TIMEOUT)
        except Exception:
            pass
        return {"today": today, "stats": stats}

    @Slot()
    def loadWordle(self):
        if not self._token:
            return
        self._set_busy(True)
        headers = self._headers()
        self._work(lambda: self._result.emit("wordle", self._wordle_now(headers)))

    @Slot(str)
    def guess(self, word: str):
        word = str(word).strip().lower()
        if len(word) < 3 or not self._token:
            return
        self._set_busy(True)
        headers = self._headers()

        def run():
            try:
                send_json(f"{API}/v1/wordle/guess", {"guess": word}, headers, timeout=TIMEOUT)
            except Exception:
                pass
            self._result.emit("wordle", self._wordle_now(headers))

        self._work(run)

    @Slot(str)
    def open(self, where: str):
        """Hand something to the website, for anything a widget should not do."""
        import webbrowser

        path = str(where or "").lstrip("/")
        webbrowser.open(f"{SITE}/{path}" if path else SITE)
