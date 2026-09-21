"""An SSH terminal, drawn by unidesk itself.

There is no browser here and no server to keep running: paramiko opens the
connection, pyte keeps the screen the far end thinks it is writing to, and the
widget paints that screen with the desk's own fonts and colours.

Three things are worth knowing about how it is put together:

  * everything that can block lives on a thread of its own. Connecting takes
    seconds, reading takes as long as the other end is quiet, and neither can
    be allowed anywhere near the thread that repaints the desk. They come back
    the only way Qt allows, which is a signal.

  * output is gathered up and applied on a timer rather than as it arrives.
    `cat` on a large file arrives as thousands of small reads, and repainting
    for each one would spend the whole session in the renderer.

  * an unknown host is a question, not a warning. Accepting whatever key turns
    up is how you end up typing a password to the wrong machine, so a host
    that is not in known_hosts stops the connection and shows its fingerprint;
    saying yes writes it to known_hosts like any other ssh client would.

One provider holds every terminal on the desk, keyed by the widget's id, so
each pane has its own session and its own screen.
"""
from __future__ import annotations

import socket
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..vault import Vault

KNOWN_HOSTS = Path.home() / ".ssh" / "known_hosts"
# How often the screen is repainted while output is pouring in.
PAINT_MS = 60
DEFAULT_SIZE = (80, 24)
# How long a read waits before looping round to check whether the pane is
# still there. Long enough that a quiet session costs nothing.
READ_TIMEOUT = 0.4

# xterm's colours, which is what we tell the far end we are.
PALETTE = {
    "black": "#1c1f26", "red": "#f2555a", "green": "#5ad67d", "brown": "#e3c07b",
    "blue": "#62a0ea", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#d5dae3",
    "brightblack": "#5c6370", "brightred": "#ff7b80", "brightgreen": "#98e8a8",
    "brightbrown": "#ffd68a", "brightblue": "#8ab4f8", "brightmagenta": "#e0a3f0",
    "brightcyan": "#7fd6e0", "brightwhite": "#ffffff",
}


class UnknownHost(Exception):
    """The far end's key is not one we have seen before."""

    def __init__(self, fingerprint: str, kind: str):
        super().__init__(fingerprint)
        self.fingerprint = fingerprint
        self.kind = kind


def _ask_first(known: dict):
    """A host key policy that refuses rather than trusts, and says what it saw."""
    import paramiko

    class Ask(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            known["hostname"] = hostname
            known["key"] = key
            raise UnknownHost(
                ":".join(f"{b:02x}" for b in key.get_fingerprint()), key.get_name()
            )

    return Ask()


def as_dict(value) -> dict:
    """What QML actually hands over for `{ host: ..., user: ... }`.

    A plain JavaScript object arrives as a QJSValue, not a dict, and calling
    dict() on it raises - which is what the Connect button did: the form
    looked like it did nothing at all, because the slot threw before it ever
    reached the connection. Asked for as a QVariantMap it converts by itself,
    but anything that still arrives raw is unwrapped here too.
    """
    unwrap = getattr(value, "toVariant", None)
    if callable(unwrap):
        value = unwrap()
    return dict(value) if isinstance(value, dict) else {}


def _accept_quietly():
    """Take whatever key is offered, and write nothing down."""
    import paramiko

    class Quiet(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            return

    return Quiet()


class _Session:
    """One connection, and the screen it writes to."""

    def __init__(self, ident: str, provider: "Terminals"):
        import pyte

        self.ident = ident
        self._provider = provider
        self.cols, self.rows = DEFAULT_SIZE
        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.ByteStream(self.screen)
        self.state = "idle"
        self.message = ""
        self.fingerprint = ""
        self.host = ""
        # What it connected with, kept so the pane can offer to save it after
        # the login works rather than before anybody knows whether it does.
        self.details: dict = {}
        self.offer = False
        self._client = None
        self._channel = None
        self._reader: threading.Thread | None = None
        self._pending = bytearray()
        self._lock = threading.Lock()

    # ---- connecting -------------------------------------------------------

    def connect(self, details: dict):
        self.details = dict(details)
        self.offer = False
        self.host = f"{details.get('user', '')}@{details.get('host', '')}"
        self._say("connecting", f"connecting to {details.get('host', '')}...")
        threading.Thread(target=self._connect, args=(details,), daemon=True).start()

    def _connect(self, details: dict):
        import paramiko

        seen: dict = {}
        client = paramiko.SSHClient()
        try:
            if KNOWN_HOSTS.exists():
                client.load_host_keys(str(KNOWN_HOSTS))
        except (OSError, paramiko.SSHException) as e:
            print(f"[unidesk] known_hosts could not be read: {e}")
        # Not AutoAddPolicy even when trusted: paramiko's version writes the
        # key into the known_hosts file it was handed, so merely connecting
        # would edit a file that belongs to every ssh client on the machine.
        # Only pressing Trust writes anything (see acceptHost).
        client.set_missing_host_key_policy(
            _accept_quietly() if details.get("trust") else _ask_first(seen)
        )
        key_path = str(details.get("key_path") or "").strip()
        try:
            client.connect(
                hostname=str(details.get("host") or ""),
                port=int(details.get("port") or 22),
                username=str(details.get("user") or "") or None,
                password=str(details.get("password") or "") or None,
                key_filename=key_path or None,
                passphrase=str(details.get("passphrase") or "") or None,
                # Without this a machine that takes passwords would still be
                # tried with every key in the agent first, which is slow and
                # can lock an account out.
                look_for_keys=bool(key_path) or not details.get("password"),
                allow_agent=True,
                timeout=15,
                auth_timeout=20,
            )
        except UnknownHost as unknown:
            self.fingerprint = unknown.fingerprint
            self._say("unknown-host", f"{unknown.kind} {unknown.fingerprint}")
            self._provider.remember_key(self.ident, seen)
            return
        except paramiko.BadHostKeyException as bad:
            # Not the same as a host we have never met. The machine answering
            # on this address is presenting a different key from the one that
            # was accepted before, which is either a rebuilt server or someone
            # standing in the middle - and either way it is not something to
            # paper over with a retry button.
            self.fingerprint = ":".join(f"{b:02x}" for b in bad.key.get_fingerprint())
            self._say("changed-host",
                      f"the key for {details.get('host', '')} is not the one saved in known_hosts")
            return
        except paramiko.AuthenticationException:
            self._say("failed", "that login was refused")
            return
        except (paramiko.SSHException, socket.error, OSError) as e:
            self._say("failed", str(e) or e.__class__.__name__)
            return

        try:
            channel = client.invoke_shell(
                term="xterm-256color", width=self.cols, height=self.rows
            )
        except paramiko.SSHException as e:
            self._say("failed", f"no shell: {e}")
            client.close()
            return

        # A timeout, not non-blocking. With no timeout at all recv() returns
        # immediately whenever the far end is quiet, which turns the reader
        # below into a spin loop - three panes of that ate every core and the
        # whole desk stopped painting, widgets and dock alike.
        channel.settimeout(READ_TIMEOUT)
        self._client, self._channel = client, channel
        # Worth offering to remember only if there is something to remember
        # and it did not come out of the vault in the first place.
        self.offer = bool(
            (self.details.get("password") or self.details.get("passphrase"))
            and not self.details.get("saved")
        )
        self._say("connected", "")
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        channel = self._channel
        while channel is not None and not channel.closed:
            try:
                data = channel.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            with self._lock:
                self._pending += data
            self._provider.output_ready(self.ident)
        if self.state == "connected":
            self._say("closed", "the connection ended")

    # ---- the screen -------------------------------------------------------

    def drain(self) -> bool:
        """Feed whatever arrived into the screen. True if anything changed."""
        with self._lock:
            if not self._pending:
                return False
            data = bytes(self._pending)
            self._pending.clear()
        self.stream.feed(data)
        return True

    def send(self, data: bytes):
        channel = self._channel
        if channel is not None and not channel.closed:
            try:
                channel.sendall(data)
            except OSError as e:
                self._say("closed", str(e))

    def resize(self, cols: int, rows: int):
        cols, rows = max(20, int(cols)), max(4, int(rows))
        if (cols, rows) == (self.cols, self.rows):
            return
        self.cols, self.rows = cols, rows
        self.screen.resize(rows, cols)
        channel = self._channel
        if channel is not None and not channel.closed:
            try:
                channel.resize_pty(width=cols, height=rows)
            except OSError:
                pass

    def close(self):
        channel, client = self._channel, self._client
        self._channel = self._client = None
        for thing in (channel, client):
            try:
                if thing is not None:
                    thing.close()
            except Exception:
                pass
        self._say("idle", "")

    def _say(self, state: str, message: str):
        self.state, self.message = state, message
        self._provider.state_changed(self.ident)


class Terminals(QObject):
    """Exposed to QML as `Terminals`: one session per widget."""

    screenChanged = Signal(str)
    stateChanged = Signal(str)
    savedChanged = Signal()
    _output = Signal(str)
    _state = Signal(str)

    def __init__(self):
        super().__init__()
        self._sessions: dict[str, _Session] = {}
        self._keys: dict[str, dict] = {}
        self._vault = Vault()
        self._paint = QTimer(self, interval=PAINT_MS, timeout=self._repaint)
        self._dirty: set[str] = set()
        # Both of these are emitted from connection threads, and both have to
        # land on the thread that owns the widgets. A signal connected
        # straight to another signal is delivered on the spot, on whatever
        # thread emitted it - so it goes through a slot, which is what makes
        # the hop. Chaining them directly meant a pane that had connected
        # perfectly well sat there saying "Connecting..." for ever.
        self._output.connect(self._on_output)
        self._state.connect(self._on_state)

    # providers are started and stopped like every other one
    def start(self):
        if not self._paint.isActive():
            self._paint.start()

    def stop(self):
        self._paint.stop()
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()

    # ---- what the threads call -------------------------------------------

    def output_ready(self, ident: str):
        self._output.emit(ident)

    def state_changed(self, ident: str):
        self._state.emit(ident)

    def remember_key(self, ident: str, seen: dict):
        self._keys[ident] = seen

    @Slot(str)
    def _on_output(self, ident: str):
        self._dirty.add(ident)

    @Slot(str)
    def _on_state(self, ident: str):
        self.stateChanged.emit(ident)

    def _repaint(self):
        for ident in list(self._dirty):
            self._dirty.discard(ident)
            session = self._sessions.get(ident)
            if session and session.drain():
                self.screenChanged.emit(ident)

    # ---- what QML calls --------------------------------------------------

    def _session(self, ident: str) -> _Session:
        session = self._sessions.get(ident)
        if session is None:
            session = self._sessions[ident] = _Session(ident, self)
        return session

    @Slot(str, "QVariantMap")
    def open(self, ident: str, details):
        """Connect this pane. `details` is what the form holds.

        Nothing is written down here. A login that turns out to be wrong is
        not worth saving, so the offer to remember it comes after it works -
        which is the way a browser does it, and the way it should be.
        """
        session = self._session(ident)
        session.close()
        session.connect(as_dict(details))

    @Slot(str, str)
    def openSaved(self, ident: str, name: str):
        """Connect to one of the saved connections, by name."""
        entry = self._vault.find(name, "ssh")
        if not entry:
            return
        details = {k: entry.get(k, "") for k in ("host", "port", "user", "key_path", "trust")}
        details.update(self._vault.secrets(name))
        details["name"] = name
        details["saved"] = True     # already in the vault; do not offer again
        self.open(ident, details)

    @Slot(str)
    def acceptHost(self, ident: str):
        """Yes, that fingerprint is the machine I meant."""
        seen = self._keys.get(ident) or {}
        key, hostname = seen.get("key"), seen.get("hostname")
        if key is not None and hostname:
            try:
                import paramiko

                KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
                KNOWN_HOSTS.touch(exist_ok=True)
                hosts = paramiko.HostKeys(str(KNOWN_HOSTS))
                hosts.add(hostname, key.get_name(), key)
                hosts.save(str(KNOWN_HOSTS))
            except Exception as e:
                print(f"[unidesk] known_hosts could not be written: {e}")

    @Slot(str)
    def close(self, ident: str):
        session = self._sessions.pop(ident, None)
        if session:
            session.close()

    @Slot(str, int, int)
    def resize(self, ident: str, cols: int, rows: int):
        session = self._sessions.get(ident)
        if session:
            session.resize(cols, rows)

    @Slot(str, str)
    def sendText(self, ident: str, text: str):
        session = self._sessions.get(ident)
        if session and text:
            session.send(text.encode("utf-8"))

    @Slot(str, int, int, str)
    def sendKey(self, ident: str, key: int, modifiers: int, text: str):
        """One keypress, in the bytes a terminal expects."""
        session = self._sessions.get(ident)
        if not session:
            return
        data = key_bytes(key, modifiers, text)
        if data:
            session.send(data)

    @Slot(str, result=bool)
    def offersSave(self, ident: str) -> bool:
        """Whether this pane has a working login that is not written down."""
        session = self._sessions.get(ident)
        return bool(session and session.offer)

    @Slot(str, result=str)
    def suggestedName(self, ident: str) -> str:
        session = self._sessions.get(ident)
        if not session:
            return ""
        details = session.details
        return str(details.get("name") or details.get("host") or "")

    @Slot(str, str)
    def saveConnection(self, ident: str, name: str):
        """Yes, remember this one."""
        session = self._sessions.get(ident)
        if not session:
            return
        details = session.details
        self._vault.save(
            {
                "name": str(name or details.get("host") or "host"),
                "kind": "ssh",
                "host": details.get("host", ""),
                "port": int(details.get("port") or 22),
                "user": details.get("user", ""),
                "key_path": details.get("key_path", ""),
            },
            {
                "password": str(details.get("password") or ""),
                "passphrase": str(details.get("passphrase") or ""),
            },
        )
        session.offer = False
        session.details["saved"] = True
        self.savedChanged.emit()
        self.stateChanged.emit(ident)

    @Slot(str)
    def declineSave(self, ident: str):
        session = self._sessions.get(ident)
        if session:
            session.offer = False
            self.stateChanged.emit(ident)

    @Slot(str, result=str)
    def html(self, ident: str) -> str:
        """The whole screen as one piece of rich text.

        One string rather than a list of rows of runs, and built here rather
        than in QML, because the pane redraws many times a second: handing
        over a thousand small objects each time, and rebuilding a text item
        per row from them, was enough to starve the thread that draws the
        entire desk - every widget stopped painting, not just this one.
        """
        session = self._sessions.get(ident)
        if not session:
            return ""
        return screen_html(screen_runs(session.screen))

    @Slot(str, result="QVariantList")
    def lines(self, ident: str) -> list:
        """The screen as rows of runs. Only the tests use this now."""
        session = self._sessions.get(ident)
        if not session:
            return []
        return screen_runs(session.screen)

    @Slot(str, result=str)
    def state(self, ident: str) -> str:
        session = self._sessions.get(ident)
        return session.state if session else "idle"

    @Slot(str, result=str)
    def message(self, ident: str) -> str:
        session = self._sessions.get(ident)
        return session.message if session else ""

    @Slot(str, result=str)
    def fingerprint(self, ident: str) -> str:
        session = self._sessions.get(ident)
        return session.fingerprint if session else ""

    @Slot(str, result=str)
    def title(self, ident: str) -> str:
        session = self._sessions.get(ident)
        return session.host if session else ""

    @Property("QVariantList", notify=savedChanged)
    def saved(self) -> list:
        return self._vault.listing("ssh")

    @Slot(str, str, result=bool)
    def rename(self, name: str, called: str) -> bool:
        """Call a saved connection something else."""
        if self._vault.rename(name, called):
            self.savedChanged.emit()
            return True
        return False

    @Slot(str)
    def forget(self, name: str):
        self._vault.forget(name)
        self.savedChanged.emit()


# ---- the parts worth testing on their own ---------------------------------

def _colour(name: str, fallback: str) -> str:
    if name in ("default", "", None):
        return fallback
    if name in PALETTE:
        return PALETTE[name]
    if len(name) == 6:
        try:
            int(name, 16)
            return f"#{name}"
        except ValueError:
            pass
    return fallback


def screen_runs(screen) -> list:
    """A pyte screen as rows of {text, fg, bg, bold} runs.

    Runs rather than characters: a row of eighty identical cells is one span
    to draw instead of eighty, and most terminal output is exactly that.
    The cursor is drawn as a reversed cell, which is always the right size
    without anybody measuring a font.
    """
    rows = []
    cursor = screen.cursor
    for y in range(screen.lines):
        line = screen.buffer[y]
        runs: list[dict] = []
        for x in range(screen.columns):
            char = line[x]
            fg, bg = _colour(char.fg, ""), _colour(char.bg, "")
            bold, reverse = bool(char.bold), bool(char.reverse)
            if not screen.cursor.hidden and y == cursor.y and x == cursor.x:
                reverse = not reverse
            if reverse:
                fg, bg = bg or "#000000", fg or "#d5dae3"
            style = (fg, bg, bold)
            if runs and runs[-1]["style"] == style:
                runs[-1]["text"] += char.data or " "
            else:
                runs.append({"style": style, "text": char.data or " ",
                             "fg": fg, "bg": bg, "bold": bold})
        for run in runs:
            run.pop("style", None)
        # Trailing blanks cost nothing to leave out, and most rows are blank.
        while runs and not runs[-1]["bg"] and not runs[-1]["text"].strip():
            runs.pop()
        rows.append(runs)
    return rows


def screen_html(rows: list) -> str:
    """Rows of runs as rich text: one <br>-separated line per row.

    Spaces become non-breaking ones because a terminal's layout IS its
    spaces, and rich text would otherwise collapse them.
    """
    out = []
    for runs in rows:
        line = []
        for run in runs:
            body = (
                str(run["text"])
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace(" ", "&nbsp;")
            )
            style = ""
            if run["fg"]:
                style += f"color:{run['fg']};"
            if run["bg"]:
                style += f"background-color:{run['bg']};"
            if run["bold"]:
                style += "font-weight:bold;"
            line.append(f'<span style="{style}">{body}</span>' if style else body)
        out.append("".join(line) or "&nbsp;")
    return "<br>".join(out)


def key_bytes(key: int, modifiers: int, text: str) -> bytes:
    """What one keypress means to a terminal.

    Qt hands over both a key code and whatever text it produced; the text is
    right for ordinary typing and useless for the keys that matter (arrows,
    Home, F5), which is why both are looked at.
    """
    ctrl = bool(modifiers & 0x04000000)  # Qt.ControlModifier
    alt = bool(modifiers & 0x08000000)   # Qt.AltModifier

    special = {
        0x01000000: b"\x1b",        # Escape
        0x01000001: b"\t",          # Tab
        0x01000003: b"\x7f",        # Backspace
        0x01000004: b"\r",          # Return
        0x01000005: b"\r",          # Enter
        0x01000006: b"\x1b[2~",     # Insert
        0x01000007: b"\x1b[3~",     # Delete
        0x01000010: b"\x1b[H",      # Home
        0x01000011: b"\x1b[F",      # End
        0x01000012: b"\x1b[D",      # Left
        0x01000013: b"\x1b[A",      # Up
        0x01000014: b"\x1b[C",      # Right
        0x01000015: b"\x1b[B",      # Down
        0x01000016: b"\x1b[5~",     # PageUp
        0x01000017: b"\x1b[6~",     # PageDown
    }
    for number, code in enumerate((b"\x1bOP", b"\x1bOQ", b"\x1bOR", b"\x1bOS")):
        special[0x01000030 + number] = code  # F1..F4
    if key in special:
        return special[key]

    if ctrl and 0x40 <= key <= 0x5F:
        # Ctrl+A..Ctrl+_ , which is where Ctrl+C lives.
        return bytes([key & 0x1F])
    if ctrl and key == 0x20:
        return b"\x00"
    if not text:
        return b""
    data = text.encode("utf-8")
    return b"\x1b" + data if alt else data
