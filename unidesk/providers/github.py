"""Code activity from GitHub, Gitea, or both merged into one picture.

GitHub: public profile, contribution calendar (scraped levels 0-4) and public
events; no token needed (a token adds the notification count).
Gitea: needs your server URL and an access token (read:user, read:repository,
read:notification); uses the heatmap, activity feed and repo APIs.
With source "both", the calendars merge day by day, totals and streaks add up,
and the activity feeds interleave by time."""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import urllib.parse

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .net import get_json, get_text


# ---- GitHub ------------------------------------------------------------------------

def _gh_describe(kind: str, p: dict) -> tuple[str, str] | None:
    cap = lambda s: (s or "")[:1].upper() + (s or "")[1:]
    size = p.get("size") or p.get("distinct_size")
    return {
        "PushEvent": (f"Pushed {size} commit{'s' if size != 1 else ''} to" if size else "Pushed to", "commit"),
        "CreateEvent": ("Created" if p.get("ref_type") == "repository" else f"Created {p.get('ref_type')} {p.get('ref') or ''} in", "add"),
        "DeleteEvent": (f"Deleted {p.get('ref_type')} {p.get('ref') or ''} in", "delete_"),
        "WatchEvent": ("Starred", "star"),
        "ForkEvent": ("Forked", "call_split"),
        "PullRequestEvent": (f"{cap(p.get('action'))} PR #{p.get('number', '')} in", "merge"),
        "IssuesEvent": (f"{cap(p.get('action'))} issue #{(p.get('issue') or {}).get('number', '')} in", "new_releases"),
        "IssueCommentEvent": (f"Commented on #{(p.get('issue') or {}).get('number', '')} in", "comment"),
        "ReleaseEvent": (f"Released {(p.get('release') or {}).get('tag_name', '')} of", "sell"),
        "PublicEvent": ("Made public", "add"),
    }.get(kind)


_CACHE = __import__("pathlib").Path(__import__("os").environ.get("LOCALAPPDATA", ".")) / "unidesk" / "github-cache.json"


def _github_levels(user: str) -> tuple[dict, int | None]:
    """Contribution levels from the public profile page (not rate limited like the API)."""
    _, html = get_text(f"https://github.com/users/{urllib.parse.quote(user)}/contributions")
    levels: dict[str, int] = {}
    for tag in re.findall(r"<td\b[^>]*>", html):
        date = re.search(r'data-date="([\d-]+)"', tag)
        level = re.search(r'data-level="(\d)"', tag)
        if date and level:
            levels[date.group(1)] = int(level.group(1))
    total = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)
    return levels, int(total.group(1).replace(",", "")) if total else None


def fetch_github_resilient(user: str, token: str) -> dict:
    """fetch_github, falling back to the last good result (with a fresh
    contribution graph) when the API refuses, e.g. the 60/hour limit."""
    import json as _json

    try:
        part = fetch_github(user, token)
        try:
            _CACHE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE.write_text(_json.dumps({"user": user.lower(), "part": part}), encoding="utf-8")
        except OSError:
            pass
        return part
    except Exception as api_error:
        try:
            cached = _json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if not cached or cached.get("user") != user.lower():
            raise api_error
        part = cached["part"]
        try:
            levels, total = _github_levels(user)
            if levels:
                part["levels"] = levels
                part["total"] = total if total is not None else part.get("total", 0)
        except Exception:
            pass
        print(f"[unidesk] GitHub API unavailable ({api_error}); using cached profile")
        return part


def fetch_github(user: str, token: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api = lambda path: get_json(f"https://api.github.com{path}", headers)
    u = urllib.parse.quote(user)
    profile = api(f"/users/{u}")
    if not profile:
        raise RuntimeError(f"no GitHub user {user!r}")
    repos = api(f"/users/{u}/repos?per_page=100&sort=pushed") or []
    events = api(f"/users/{u}/events/public?per_page=30") or []
    _, html = get_text(f"https://github.com/users/{u}/contributions")

    levels: dict[str, int] = {}
    for tag in re.findall(r"<td\b[^>]*>", html):
        date = re.search(r'data-date="([\d-]+)"', tag)
        level = re.search(r'data-level="(\d)"', tag)
        if date and level:
            levels[date.group(1)] = int(level.group(1))
    total = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)

    notifications = None
    if token:
        try:
            notifications = len(api("/notifications?per_page=50") or [])
        except Exception:
            notifications = None

    login = profile["login"]
    activity = []
    for e in events:
        described = _gh_describe(e.get("type", ""), e.get("payload") or {})
        if not described:
            continue
        repo = (e.get("repo") or {}).get("name", "")
        activity.append({
            "text": described[0], "icon": described[1], "source": "github",
            "repo": repo[len(login) + 1:] if repo.startswith(login + "/") else repo,
            "url": f"https://github.com/{repo}", "at": e.get("created_at", ""),
        })
    return {
        "source": "github", "login": login, "name": profile.get("name") or login,
        "avatar": profile.get("avatar_url", ""), "url": profile.get("html_url", f"https://github.com/{login}"),
        "repos": profile.get("public_repos", 0), "followers": profile.get("followers", 0),
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "levels": levels, "total": int(total.group(1).replace(",", "")) if total else sum(1 for v in levels.values() if v),
        "activity": activity, "notifications": notifications,
    }


# ---- Gitea -------------------------------------------------------------------------

_GITEA_OPS = {
    "commit_repo": ("Pushed to", "commit"), "mirror_sync_push": ("Mirrored to", "commit"),
    "create_repo": ("Created", "add"), "rename_repo": ("Renamed", "sell"), "transfer_repo": ("Transferred", "call_split"),
    "star_repo": ("Starred", "star"), "watch_repo": ("Watched", "star"),
    "create_issue": ("Opened an issue in", "new_releases"), "close_issue": ("Closed an issue in", "check"),
    "reopen_issue": ("Reopened an issue in", "new_releases"), "comment_issue": ("Commented in", "comment"),
    "create_pull_request": ("Opened a PR in", "merge"), "merge_pull_request": ("Merged a PR in", "merge"),
    "close_pull_request": ("Closed a PR in", "merge"), "reopen_pull_request": ("Reopened a PR in", "merge"),
    "approve_pull_request": ("Approved a PR in", "check"), "reject_pull_request": ("Requested changes in", "comment"),
    "comment_pull": ("Reviewed a PR in", "comment"), "push_tag": ("Tagged", "sell"), "publish_release": ("Released", "sell"),
    "delete_branch": ("Deleted a branch in", "delete_"), "delete_tag": ("Deleted a tag in", "delete_"),
}


def fetch_gitea(base: str, token: str) -> dict:
    base = base.rstrip("/")
    if not re.match(r"^https?://", base):
        base = "https://" + base
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    api = lambda path: get_json(f"{base}/api/v1{path}", headers)

    me = api("/user")
    if not me:
        raise RuntimeError("Gitea did not accept the token (check gitea_token)")
    login = me["login"]
    u = urllib.parse.quote(login)

    levels_counts: dict[str, int] = {}
    for bucket in api(f"/users/{u}/heatmap") or []:
        day = dt.datetime.fromtimestamp(int(bucket["timestamp"])).date().isoformat()
        levels_counts[day] = levels_counts.get(day, 0) + int(bucket.get("contributions", 0))

    repos = api("/user/repos?limit=50") or []
    try:
        feeds = api(f"/users/{u}/activities/feeds?limit=30") or []
    except Exception:
        feeds = []  # older Gitea without the feeds API
    notifications = None
    try:
        notifications = len(api("/notifications?limit=50") or [])
    except Exception:
        pass

    activity = []
    for f in feeds:
        op = f.get("op_type", "")
        text, icon = _GITEA_OPS.get(op, (None, None))
        if not text:
            continue
        if op == "commit_repo":
            try:
                n = len(json.loads(f.get("content") or "{}").get("Commits") or [])
                if n:
                    text = f"Pushed {n} commit{'s' if n != 1 else ''} to"
            except ValueError:
                pass
        repo = (f.get("repo") or {}).get("full_name", "")
        activity.append({
            "text": text, "icon": icon, "source": "gitea",
            "repo": repo[len(login) + 1:] if repo.startswith(login + "/") else repo,
            "url": f"{base}/{repo}", "at": f.get("created", ""),
        })

    return {
        "source": "gitea", "login": login, "name": me.get("full_name") or login,
        "avatar": me.get("avatar_url", ""), "url": f"{base}/{login}",
        "repos": len(repos), "followers": me.get("followers_count", 0),
        "stars": sum(r.get("stars_count", 0) for r in repos),
        "counts": levels_counts, "total": sum(levels_counts.values()),
        "activity": activity, "notifications": notifications,
    }


def _count_levels(counts: dict[str, int]) -> dict[str, int]:
    """Turn raw daily counts into GitHub-style levels 1-4 by quartile."""
    values = sorted(v for v in counts.values() if v > 0)
    if not values:
        return {}
    q = lambda f: values[min(len(values) - 1, int(len(values) * f))]
    cuts = (q(0.25), q(0.5), q(0.75))
    return {d: (1 + sum(v > c for c in cuts)) for d, v in counts.items() if v > 0}


# ---- merging -----------------------------------------------------------------------

def combine(parts: list[dict], weeks_wanted: int, profile: str = "github") -> dict:
    merged_levels: dict[str, int] = {}
    for part in parts:
        levels = part.get("levels") if "levels" in part else _count_levels(part.get("counts", {}))
        for day, level in levels.items():
            if level <= 0:
                continue
            prev = merged_levels.get(day, 0)
            merged_levels[day] = min(4, max(prev, level) + (1 if prev else 0))

    today = dt.date.today()
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7 + (weeks_wanted - 1) * 7)
    weeks = []
    for w in range(weeks_wanted):
        week = []
        for d in range(7):
            day = start + dt.timedelta(days=w * 7 + d)
            week.append(-1 if day > today else merged_levels.get(day.isoformat(), 0))
        weeks.append(week)

    streak, cursor = 0, today
    if not merged_levels.get(cursor.isoformat()):
        cursor -= dt.timedelta(days=1)
    while merged_levels.get(cursor.isoformat(), 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)

    main = next((p for p in parts if p["source"] == profile), parts[0])
    activity = sorted((a for p in parts for a in p["activity"]), key=lambda a: a["at"] or "", reverse=True)
    notes = [p["notifications"] for p in parts if p.get("notifications") is not None]
    return {
        "sources": [p["source"] for p in parts],
        "accounts": [{"source": p["source"], "login": p["login"], "url": p["url"]} for p in parts],
        "login": main["login"], "name": main["name"], "avatar": main["avatar"], "url": main["url"],
        "repos": sum(p["repos"] for p in parts), "followers": sum(p["followers"] for p in parts),
        "stars": sum(p["stars"] for p in parts), "contributions": sum(p["total"] for p in parts),
        "streak": streak, "weeks": weeks, "activity": activity[:8],
        "notifications": sum(notes) if notes else None,
    }


class GitHub(QObject):
    """Exposed to QML as `GitHub` (it covers Gitea too): `GitHub.data.contributions`, `.weeks`, ..."""

    dataChanged = Signal()
    errorChanged = Signal()
    _ready = Signal("QVariant", str)

    def __init__(self):
        super().__init__()
        self._data = None
        self._error = ""
        self._settings: dict = {}
        self.weeks = 24
        self._timer = QTimer(self, interval=15 * 60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def configure(self, settings: dict):
        settings = dict(settings or {})
        if settings == self._settings:
            return
        self._settings = settings
        if self._timer.isActive():
            self.refresh()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        threading.Thread(target=self._fetch, args=(dict(self._settings), self.weeks), daemon=True).start()

    def _fetch(self, s: dict, weeks: int):
        source = str(s.get("source") or "github").lower()
        parts, errors = [], []
        if source in ("github", "both") and s.get("github_user"):
            try:
                parts.append(fetch_github_resilient(str(s["github_user"]).strip(), str(s.get("github_token") or "").strip()))
            except Exception as e:
                errors.append(f"GitHub: {e}")
        if source in ("gitea", "both"):
            if s.get("gitea_url") and s.get("gitea_token"):
                try:
                    parts.append(fetch_gitea(str(s["gitea_url"]).strip(), str(s["gitea_token"]).strip()))
                except Exception as e:
                    errors.append(f"Gitea: {e}")
            else:
                errors.append("Gitea: set gitea_url and gitea_token in Settings")
        if not parts and not errors:
            errors.append("Add your GitHub username or Gitea details: right-click a widget, then Settings")
        profile = str(s.get("profile") or "github").lower()
        parts.sort(key=lambda p: 0 if p["source"] == profile else 1)
        data = combine(parts, weeks, profile) if parts else None
        for e in errors:
            print(f"[unidesk] {e}")
        self._ready.emit(data, " · ".join(errors))

    @Slot("QVariant", str)
    def _on_ready(self, data, error: str):
        if data is not None or not self._data:
            self._data = data
            self.dataChanged.emit()
        if error != self._error:
            self._error = error
            self.errorChanged.emit()

    @Property("QVariant", notify=dataChanged)
    def data(self):
        return self._data

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error
