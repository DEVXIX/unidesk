"""Now playing + synced lyrics.

Now playing comes from media-bridge.exe (the Windows media session over
stdio); covers are written to a small cache folder so QML and the colour
extractor can read them as files. Lyrics come from lrclib.net."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from .net import get_json

CACHE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk" / "art"
CREATE_NO_WINDOW = 0x08000000


def bridge_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for candidate in (base / "media-bridge" / "media-bridge.exe", base / "resources" / "media-bridge" / "media-bridge.exe"):
        if candidate.exists():
            return candidate
    return base / "resources" / "media-bridge" / "media-bridge.exe"


class Media(QObject):
    """Exposed to QML as `Media`."""

    playingChanged = Signal()
    lyricsChanged = Signal()
    artChanged = Signal(str)  # file path or ""
    _line = Signal(str)
    _lyrics_ready = Signal(str, "QVariantMap")

    def __init__(self):
        super().__init__()
        self._playing: dict | None = None
        self._art_url = ""
        self._art_path = ""
        self._lyrics: dict = {"key": "", "lines": [], "plain": "", "loading": False}
        self._lyrics_key = ""
        self._proc: subprocess.Popen | None = None
        self._stopping = False
        self.want_lyrics = False
        self._line.connect(self._on_line)
        self._lyrics_ready.connect(self._on_lyrics)
        CACHE.mkdir(parents=True, exist_ok=True)
        for old in CACHE.glob("*"):
            old.unlink(missing_ok=True)

    # ---- bridge process --------------------------------------------------------

    def start(self):
        if self._proc:
            return
        exe = bridge_path()
        if not exe.exists():
            print(f"[unidesk] media bridge not found at {exe}; run: dotnet publish media-bridge -c Release -o resources/media-bridge")
            return
        self._proc = subprocess.Popen(
            [str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW, bufsize=0,
        )
        threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()

    def stop(self):
        self._stopping = True
        if self._proc:
            self._proc.kill()

    def _read(self, proc: subprocess.Popen):
        for raw in iter(proc.stdout.readline, b""):
            self._line.emit(raw.decode("utf-8", "replace"))
        if not self._stopping:
            self._proc = None
            QTimer.singleShot(3000, self.start)

    def _send(self, command: str):
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write((command + "\n").encode())
                self._proc.stdin.flush()
            except OSError:
                pass

    @Slot(str)
    def _on_line(self, line: str):
        try:
            msg = json.loads(line)
        except ValueError:
            return
        if msg.get("type") != "media":
            return
        p = msg.get("playing")
        if not p:
            self._playing = None
            self._set_art("")
            self.playingChanged.emit()
            return
        if "art" in p:
            self._set_art(self._store_art(p.pop("art") or ""))
        p["art"] = self._art_url
        p["artist"] = p.get("artist") or ""
        p["album"] = p.get("album") or ""
        p["receivedAt"] = time.time() * 1000
        self._playing = p
        self.playingChanged.emit()
        if self.want_lyrics:
            self._fetch_lyrics(p)

    def _store_art(self, data_url: str) -> str:
        m = re.match(r"data:image/(\w+);base64,(.*)", data_url, re.S)
        if not m:
            return ""
        data = base64.b64decode(m.group(2))
        path = CACHE / f"{hashlib.sha1(data).hexdigest()[:16]}.{ 'png' if m.group(1) == 'png' else 'jpg'}"
        if not path.exists():
            for old in sorted(CACHE.glob("*"), key=lambda f: f.stat().st_mtime)[:-8]:
                old.unlink(missing_ok=True)
            path.write_bytes(data)
        return str(path)

    def _set_art(self, path: str):
        if path == self._art_path:
            return
        self._art_path = path
        self._art_url = QUrl.fromLocalFile(path).toString() if path else ""
        self.artChanged.emit(path)

    # ---- lyrics ----------------------------------------------------------------

    def _fetch_lyrics(self, p: dict):
        key = f"{p['title']}{p['artist']}"
        if key == self._lyrics_key:
            return
        self._lyrics_key = key
        self._lyrics = {"key": key, "lines": [], "plain": "", "loading": True}
        self.lyricsChanged.emit()
        track = dict(title=p["title"], artist=p["artist"], album=p["album"], duration=p.get("duration") or 0)
        threading.Thread(target=lambda: self._lyrics_ready.emit(key, lookup_lyrics(track)), daemon=True).start()

    @Slot(str, "QVariantMap")
    def _on_lyrics(self, key: str, lyrics: dict):
        if key != self._lyrics_key:
            return
        self._lyrics = {"key": key, **lyrics, "loading": False}
        self.lyricsChanged.emit()

    # ---- QML -------------------------------------------------------------------

    @Property("QVariant", notify=playingChanged)
    def playing(self):
        return self._playing

    @Property("QVariantMap", notify=lyricsChanged)
    def lyrics(self):
        return self._lyrics

    @Slot()
    def playPause(self):
        self._send("play-pause")

    @Slot()
    def next(self):
        self._send("next")

    @Slot()
    def previous(self):
        self._send("previous")

    @Slot(float)
    def seek(self, seconds: float):
        self._send(f"seek {max(0.0, seconds):.2f}")


# ---- lrclib ----------------------------------------------------------------------

_API = "https://lrclib.net/api"
_cache: dict[str, dict] = {}
_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s*[(\[{][^)\]}]*(official|video|audio|lyric|visuali[sz]er|remaster|live|version|edit|mix)[^)\]}]*[)\]}]", "", text)
    text = re.sub(r"\s*[(\[{]?\s*\b(feat|ft)\.?\s+[^)\]}]*[)\]}]?", "", text)
    return re.sub(r"[\W_]+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    def grams(s):
        s = f" {s} "
        out: dict[str, int] = {}
        for i in range(len(s) - 1):
            out[s[i:i + 2]] = out.get(s[i:i + 2], 0) + 1
        return out

    ga, gb = grams(na), grams(nb)
    shared = sum(min(c, gb.get(g, 0)) for g, c in ga.items())
    total = sum(ga.values()) + sum(gb.values())
    return 2 * shared / total if total else 0.0


def _score(track: dict, r: dict) -> float:
    title = _similarity(track["title"], r.get("trackName") or "")
    if title < 0.5:
        return 0.0
    names = [n.strip() for n in re.split(r",|&|\bfeat\.?\b|\bft\.?\b|\bx\b", track["artist"], flags=re.I) if n.strip()]
    artist = _similarity(track["artist"], r.get("artistName") or "") if track["artist"] else 0.5
    for n in names:
        artist = max(artist, _similarity(n, r.get("artistName") or ""))
    value = 0.65 * title + 0.35 * artist
    if track["duration"] and r.get("duration"):
        off = abs(track["duration"] - r["duration"])
        if off > 10:
            value -= min(0.3, (off - 10) / 100)
    if not r.get("syncedLyrics") and not r.get("plainLyrics"):
        value -= 0.2
    return value


def _parse_lrc(lrc: str) -> list[dict]:
    lines = []
    for raw in lrc.splitlines():
        stamps = list(_TIMESTAMP.finditer(raw))
        if not stamps:
            continue
        text = _TIMESTAMP.sub("", raw).strip()
        for s in stamps:
            t = int(s.group(1)) * 60 + int(s.group(2)) + (float(f"0.{s.group(3)}") if s.group(3) else 0)
            lines.append({"time": t, "text": text})
    return sorted(lines, key=lambda line: line["time"])


def lookup_lyrics(track: dict) -> dict:
    key = f"{track['title']}{track['artist']}"
    if key in _cache:
        return _cache[key]
    none = {"lines": [], "plain": ""}
    try:
        record = None
        if track["artist"].strip():
            q = {"artist_name": track["artist"], "track_name": track["title"]}
            if track["album"]:
                q["album_name"] = track["album"]
            if track["duration"]:
                q["duration"] = str(round(track["duration"]))
            record = get_json(f"{_API}/get?{urllib.parse.urlencode(q)}")
        if not record:
            results = get_json(f"{_API}/search?{urllib.parse.urlencode({'q': (track['title'] + ' ' + track['artist']).strip()})}") or []
            best = 0.0
            for r in results:
                s = _score(track, r)
                if s > best:
                    best, record = s, r
        if not record or record.get("instrumental"):
            result = none
        else:
            result = {
                "lines": _parse_lrc(record.get("syncedLyrics") or ""),
                "plain": (record.get("plainLyrics") or "").strip(),
            }
        if len(_cache) > 50:
            _cache.pop(next(iter(_cache)))
        _cache[key] = result
        return result
    except Exception as e:  # network trouble: not cached, next song retries
        print(f"[unidesk] lyrics lookup failed: {e}")
        return none
