"""League of Legends: rank and recent games from the League client's local API
(no Riot key needed; works while the client is open, and shows the last
results it saw when it's closed)."""
from __future__ import annotations

import base64
import json
import os
import ssl
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk"
CACHE = HOME / "league.json"
ASSETS = HOME / "league-assets"
LOCKFILES = [Path(r"C:\Riot Games\League of Legends\lockfile"), Path(r"D:\Riot Games\League of Legends\lockfile")]
_NO_VERIFY = ssl.create_default_context()
_NO_VERIFY.check_hostname = False
_NO_VERIFY.verify_mode = ssl.CERT_NONE  # the client uses a self-signed certificate on 127.0.0.1


def _client():
    for lockfile in LOCKFILES:
        try:
            _, _, port, password, protocol = lockfile.read_text(encoding="utf-8").split(":")
            auth = base64.b64encode(f"riot:{password}".encode()).decode()
            return f"{protocol}://127.0.0.1:{port}", auth
        except (OSError, ValueError):
            continue
    return None


def _get(base: str, auth: str, path: str, raw: bool = False):
    req = urllib.request.Request(base + path, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5, context=_NO_VERIFY) as res:
        data = res.read()
    return data if raw else json.loads(data.decode("utf-8"))


def _asset(base: str, auth: str, path: str) -> str:
    ASSETS.mkdir(parents=True, exist_ok=True)
    target = ASSETS / path.strip("/").replace("/", "_")
    if not target.exists():
        try:
            target.write_bytes(_get(base, auth, path, raw=True))
        except Exception:
            return ""
    return QUrl.fromLocalFile(str(target)).toString()


def fetch() -> dict | None:
    client = _client()
    if not client:
        return None
    base, auth = client
    me = _get(base, auth, "/lol-summoner/v1/current-summoner")
    ranked = _get(base, auth, "/lol-ranked/v1/current-ranked-stats")
    queues = {q.get("queueType"): q for q in ranked.get("queues", [])}
    solo = queues.get("RANKED_SOLO_5x5") or {}
    flex = queues.get("RANKED_FLEX_SR") or {}
    history = _get(base, auth, "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=9")
    games = []
    for g in (history.get("games") or {}).get("games", [])[:10]:
        p = (g.get("participants") or [{}])[0]
        stats = p.get("stats", {})
        champ = p.get("championId", 0)
        games.append({
            "win": bool(stats.get("win")), "champion": _asset(base, auth, f"/lol-game-data/assets/v1/champion-icons/{champ}.png"),
            "kills": stats.get("kills", 0), "deaths": stats.get("deaths", 0), "assists": stats.get("assists", 0),
            "mode": g.get("gameMode", ""), "at": g.get("gameCreation", 0), "minutes": round(g.get("gameDuration", 0) / 60),
        })

    def rank(q):
        tier = str(q.get("tier") or "").capitalize()
        if not tier or tier in ("None", "Unranked"):
            return {"tier": "Unranked", "division": "", "lp": 0, "wins": 0, "losses": 0}
        return {"tier": tier, "division": q.get("division", "") if q.get("division") != "NA" else "",
                "lp": q.get("leaguePoints", 0), "wins": q.get("wins", 0), "losses": q.get("losses", 0)}

    streak = 0
    for game in games:
        if not games or game["win"] != games[0]["win"]:
            break
        streak += 1
    return {
        "name": me.get("gameName") or me.get("displayName", ""), "tag": me.get("tagLine", ""),
        "level": me.get("summonerLevel", 0), "icon": _asset(base, auth, f"/lol-game-data/assets/v1/profile-icons/{me.get('profileIconId', 0)}.jpg"),
        "solo": rank(solo), "flex": rank(flex), "games": games,
        "streak": streak * (1 if games and games[0]["win"] else -1), "live": True,
    }


EMBLEM_URL = "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-emblem/emblem-{}.png"
TIERS = ("iron", "bronze", "silver", "gold", "platinum", "emerald", "diamond", "master", "grandmaster", "challenger")


def _download_emblems():
    """Riot's ranked emblems, fetched once into the cache so they load instantly (and offline)."""
    from .net import USER_AGENT

    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage

    ASSETS.mkdir(parents=True, exist_ok=True)
    for tier in TIERS:
        target = ASSETS / f"emblem-{tier}-256.png"
        if target.exists():
            continue
        try:
            req = urllib.request.Request(EMBLEM_URL.format(tier), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as res:
                image = QImage.fromData(res.read())
            # The files are 16:9 (1280x720, some 2560x1440) with the crest in the
            # middle: crop the same share of each so tiers keep their relative sizes.
            side = int(image.width() * 0.3)
            crop = image.copy(QRect(image.width() // 2 - side // 2, int(image.height() * 0.475) - side // 2, side, side))
            crop.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save(str(target))
        except Exception as e:
            print(f"[unidesk] rank emblem {tier} failed: {e}")


class League(QObject):
    """Exposed to QML as `League`: `.data` (null until the client has been seen once)."""

    changed = Signal()
    _ready = Signal("QVariant")

    def __init__(self):
        super().__init__()
        try:
            self._data = json.loads(CACHE.read_text(encoding="utf-8"))
            self._data["live"] = False
        except (OSError, ValueError):
            self._data = None
        self._timer = QTimer(self, interval=60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()
            threading.Thread(target=lambda: (_download_emblems(), self.changed.emit()), daemon=True).start()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        def work():
            try:
                self._ready.emit(fetch())
            except Exception as e:
                print(f"[unidesk] league client not reachable: {e}")
                self._ready.emit(None)

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariant")
    def _on_ready(self, data):
        if data:
            self._data = data
            try:
                HOME.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(data), encoding="utf-8")
            except OSError:
                pass
        elif self._data and self._data.get("live"):
            self._data = {**self._data, "live": False}
        else:
            return
        self.changed.emit()

    @Property("QVariant", notify=changed)
    def data(self):
        return self._data

    @Slot(str, result=str)
    def emblem(self, tier: str) -> str:
        """Rank emblem for a tier: the cached file, or the web address until it's cached."""
        name = str(tier).lower()
        if name not in TIERS:
            return ""
        cached = ASSETS / f"emblem-{name}-256.png"
        return QUrl.fromLocalFile(str(cached)).toString() if cached.exists() else EMBLEM_URL.format(name)
