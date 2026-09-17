"""Recently played games from Steam, Epic and Riot, with cover art and a launch link."""
from __future__ import annotations

import json
import os
import re
import threading
import winreg
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

ICONS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk" / "icons"
SKIP_STEAM = re.compile(r"steamworks|redistributable|proton|steam linux runtime|soundtrack|dedicated server|sdk", re.I)


def _vdf_pairs(text: str) -> list[tuple[str, str]]:
    return re.findall(r'"([^"]+)"\s+"([^"]*)"', text)


def steam_games() -> list[dict]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return []
    libraries = {steam}
    try:
        for k, v in _vdf_pairs((steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")):
            if k == "path":
                libraries.add(Path(v.replace("\\\\", "\\")))
    except OSError:
        pass
    games = []
    for lib in libraries:
        for manifest in (lib / "steamapps").glob("appmanifest_*.acf"):
            try:
                fields = dict(_vdf_pairs(manifest.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
            appid, name = fields.get("appid", ""), fields.get("name", "")
            if not appid or not name or SKIP_STEAM.search(name):
                continue
            cover = ""
            cache = steam / "appcache" / "librarycache" / appid
            for candidate in [cache / "library_600x900.jpg", *cache.glob("**/library_600x900.jpg"), steam / "appcache" / "librarycache" / f"{appid}_library_600x900.jpg"]:
                if candidate.exists():
                    cover = QUrl.fromLocalFile(str(candidate)).toString()
                    break
            if not cover:
                cover = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
            games.append({
                "name": name, "store": "steam", "cover": cover, "tall": True,
                "launch": f"steam://rungameid/{appid}", "lastPlayed": int(fields.get("LastPlayed") or 0),
            })
    return games


def epic_games() -> list[dict]:
    games = []
    for item in Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests").glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "games" not in [c.lower() for c in data.get("AppCategories", ["games"])]:
            continue
        exe = Path(data.get("InstallLocation", "")) / data.get("LaunchExecutable", "")
        played = exe.stat().st_atime if exe.exists() else item.stat().st_mtime
        games.append({
            "name": data.get("DisplayName", ""), "store": "epic", "cover": _icon(str(exe)), "tall": False,
            "launch": f"com.epicgames.launcher://apps/{data.get('CatalogNamespace')}%3A{data.get('CatalogItemId')}%3A{data.get('AppName')}?action=launch&silent=true",
            "lastPlayed": int(played),
        })
    return games


def riot_games() -> list[dict]:
    root = Path(r"C:\Riot Games")
    client = root / "Riot Client" / "RiotClientServices.exe"
    if not client.exists():
        return []
    products = [
        ("League of Legends", "league_of_legends", root / "League of Legends", "LeagueClient.exe"),
        ("VALORANT", "valorant", root / "VALORANT", "live/VALORANT.exe"),
        ("Teamfight Tactics", "league_of_legends", root / "Teamfight Tactics", ""),
    ]
    games = []
    for name, product, folder, exe in products:
        if not folder.exists():
            continue
        logs = [p for p in (folder / "Logs", folder) if p.exists()]
        played = max(p.stat().st_mtime for p in logs)
        games.append({
            "name": name, "store": "riot", "cover": _icon(str(folder / exe)) if exe else _icon(str(client)), "tall": False,
            "launch": f'"{client}" --launch-product={product} --launch-patchline=live', "lastPlayed": int(played),
        })
    return games


def _icon(path: str) -> str:
    from ..dock import winapi

    if not path or not Path(path).exists():
        return ""
    try:
        png = winapi.icon_png(path, 256, ICONS)
        return QUrl.fromLocalFile(png).toString() if png else ""
    except Exception:
        return ""


class Games(QObject):
    """Exposed to QML as `Games`: `.recent`, launch(index)."""

    changed = Signal()
    _ready = Signal("QVariantList")

    def __init__(self):
        super().__init__()
        self._games: list[dict] = []
        self._timer = QTimer(self, interval=10 * 60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        def work():
            from ..dock import winapi

            winapi.com_init()
            games = []
            for source in (steam_games, epic_games, riot_games):
                try:
                    games += source()
                except Exception as e:
                    print(f"[unidesk] games ({source.__name__}) failed: {e}")
            games.sort(key=lambda g: -g["lastPlayed"])
            self._ready.emit(games[:24])

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList")
    def _on_ready(self, games):
        self._games = list(games)
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def recent(self):
        return self._games

    @Slot(int)
    def launch(self, index: int):
        if not 0 <= index < len(self._games):
            return
        target = self._games[index]["launch"]
        try:
            if target.startswith('"'):
                import subprocess

                subprocess.Popen(target, creationflags=0x00000008 | 0x00000200)
            else:
                os.startfile(target)
        except OSError as e:
            print(f"[unidesk] could not launch game: {e}")
