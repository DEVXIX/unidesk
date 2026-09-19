"""Open an xD game in a window of its own, rather than in a browser tab.

The arcade games are Flash - twenty-seven .swf files played through Ruffle, a
Flash emulator compiled to WebAssembly. There is no version of those that a
Qt widget can draw: they need a browser engine, and the only question is whose
and where.

This uses the one already on the machine, in app mode. `--app=<url>` opens a
window with no tabs, no address bar and no bookmarks - a page in a frame,
which for a game is the whole point.

Signing in is the awkward part. xD keeps its session in localStorage, not in a
cookie, so there is nothing a browser would pick up on its own and nothing that
can be passed in the address - the game window opened on a login form while the
widget was signed in the whole time. So the widget hands its own token over:
the window runs in a profile of unidesk's own, and the token is written into
that profile's localStorage over Chrome's debugging protocol before the page
is reloaded.

A profile of our own is what makes that possible (Chrome refuses remote
debugging on the normal one) and it also keeps all of this away from the
browser somebody actually uses. Its only contents are whatever xD stores.

The window is sized and placed by us: arcade games get most of the screen,
because a Club Penguin game in a small frame is unplayable, and the daily ones
get something closer to a page.

What this cannot do is theme the window or draw inside it. It is somebody
else's browser in a borderless frame - that is the trade against shipping a
hundred and sixty megabytes of Qt WebEngine to do it ourselves.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

# In preference order. Every one of these takes --app and --window-size; Edge
# is on every Windows 11 machine, so the list cannot come up empty.
BROWSERS = (
    ("chrome.exe", ("Google", "Chrome", "Application")),
    ("msedge.exe", ("Microsoft", "Edge", "Application")),
    ("brave.exe", ("BraveSoftware", "Brave-Browser", "Application")),
    ("vivaldi.exe", ("Vivaldi", "Application")),
)

# How long to wait for the window to exist before giving up on signing it in.
# It still opens; it just opens on the login form.
SIGN_IN_TIMEOUT = 12

# The debugging port is fixed rather than picked per launch, and it has to be.
# A browser already running with a profile does not start a second process for
# it: the new invocation hands its arguments to the existing one and exits, so
# every flag after the first launch - including a fresh port - is dropped on
# the floor. The first window opens the port; a fixed number is how the ones
# after it can still find it.
DEBUG_PORT = 9711

# How much of the screen a game gets, and the smallest it is worth opening.
ARCADE_FRACTION = 0.78
DAILY_FRACTION = 0.52
MIN_SIZE = (900, 640)


def _program_dirs() -> list[Path]:
    out = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            out.append(Path(value))
    return out


def browser() -> str | None:
    """The first Chromium-based browser on this machine, or None."""
    for exe, parts in BROWSERS:
        found = shutil.which(exe)
        if found:
            return found
        for root in _program_dirs():
            candidate = root.joinpath(*parts, exe)
            if candidate.exists():
                return str(candidate)
    return None


def _geometry(big: bool) -> tuple[int, int, int, int]:
    """A window that fills its share of the screen, centred."""
    try:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
    except Exception:
        area = None
    if area is None:
        return (MIN_SIZE[0], MIN_SIZE[1], 80, 80)

    fraction = ARCADE_FRACTION if big else DAILY_FRACTION
    width = max(MIN_SIZE[0], int(area.width() * fraction))
    height = max(MIN_SIZE[1], int(area.height() * fraction))
    width, height = min(width, area.width()), min(height, area.height())
    x = area.x() + (area.width() - width) // 2
    y = area.y() + (area.height() - height) // 2
    return (width, height, x, y)


def _profile() -> Path:
    """unidesk's own browser profile: game windows only, nothing else."""
    home = Path(os.environ.get("LOCALAPPDATA", ".")) / "unidesk" / "xd-games"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _origin(url: str) -> str:
    """Just the scheme and host: what a redirect cannot change."""
    parts = url.split("/", 3)
    return "/".join(parts[:3]) if len(parts) >= 3 else url


def _target(port: int, deadline: float, url: str) -> dict | None:
    """The window that was just opened, once it can be talked to.

    Matched by SITE rather than by address. A window opened while signed out
    redirects to the login page before anyone can look at it, so waiting for
    the game's own address is waiting for something that will not appear - and
    the sign-in it was waiting to do is exactly what stops the redirect.

    The newest matching window wins: earlier ones have been dealt with already.
    """
    wanted = _origin(url)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as res:
                pages = [
                    entry
                    for entry in json.loads(res.read().decode("utf-8", "replace"))
                    if entry.get("type") == "page" and entry.get("webSocketDebuggerUrl")
                ]
            for entry in reversed(pages):
                if str(entry.get("url", "")).startswith(wanted):
                    return entry
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _sign_in(port: int, token: str, user_id: str, url: str) -> bool:
    """Put the widget's session into the window's localStorage, and reload."""
    try:
        import websocket
    except ImportError:
        return False

    target = _target(port, time.monotonic() + SIGN_IN_TIMEOUT, url)
    if not target:
        return False
    try:
        # No Origin header: Chrome refuses a debugging socket that carries one
        # it was not told to expect, and having none is simpler than matching.
        connection = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=8, suppress_origin=True
        )
    except Exception:
        return False
    try:
        # json.dumps for both, so a token with a quote in it cannot end the
        # string it is being written into.
        # Sent to the game, not reloaded. By the time the token lands the
        # window is on the login page - reloading that just signs in and goes
        # to the home page, which is not the game anybody asked for.
        script = (
            f"localStorage.setItem('auth_token', {json.dumps(token)});"
            f"localStorage.setItem('auth_user_id', {json.dumps(str(user_id))});"
            f"location.replace({json.dumps(url)});"
        )
        connection.send(
            json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": script}})
        )
        # The reply is waited for so the reload has been asked for before this
        # returns; without it the connection can close first and take the
        # evaluation with it.
        connection.recv()
        return True
    except Exception:
        return False
    finally:
        try:
            connection.close()
        except Exception:
            pass


def open_game(url: str, big: bool = False, token: str = "", user_id: str = "") -> bool:
    """Open one game in its own window, signed in. Answers whether it opened."""
    exe = browser()
    if not exe:
        return False
    width, height, x, y = _geometry(big)
    try:
        subprocess.Popen(
            [
                exe,
                f"--app={url}",
                f"--window-size={width},{height}",
                f"--window-position={x},{y}",
                f"--user-data-dir={_profile()}",
                f"--remote-debugging-port={DEBUG_PORT}",
                # Chrome 111 and later refuse a debugging websocket whose
                # Origin it was not told to expect, and say so in the rejection.
                # Scoped to the one origin ours comes from rather than "*".
                f"--remote-allow-origins=http://127.0.0.1:{DEBUG_PORT}",
                # This profile exists to hold one site's session. Nothing about
                # it should nag, sync, or offer to become the default browser.
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except Exception as e:
        print(f"[unidesk] xD game: {e}")
        return False

    if token:
        # Best effort: a window that could not be signed in still opened, and
        # signing in by hand there works and is remembered.
        if not _sign_in(DEBUG_PORT, token, user_id, url):
            print("[unidesk] xD game: opened, but the session could not be handed over")
    return True
