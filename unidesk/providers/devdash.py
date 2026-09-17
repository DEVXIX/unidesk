"""Open pull requests / issues and CI runs from GitHub and Gitea, using the
accounts in Settings > Code activity."""
from __future__ import annotations

import threading
import urllib.parse

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .net import get_json


def _github(user: str, token: str, repos: list[str]) -> tuple[list, list]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    items = []
    for query, kind in ((f"is:open is:pr involves:{user}", "pr"), (f"is:open is:issue assignee:{user}", "issue")):
        data = get_json(f"https://api.github.com/search/issues?per_page=15&sort=updated&q={urllib.parse.quote(query)}", headers) or {}
        for it in data.get("items", []):
            repo = it.get("repository_url", "").split("/repos/")[-1]
            items.append({
                "source": "github", "kind": kind, "title": it.get("title", ""), "repo": repo, "number": it.get("number"),
                "url": it.get("html_url", ""), "updated": it.get("updated_at", ""), "draft": bool(it.get("draft")),
                "review": kind == "pr" and it.get("user", {}).get("login", "").lower() != user.lower(),
            })
    runs = []
    for repo in repos:
        data = get_json(f"https://api.github.com/repos/{repo}/actions/runs?per_page=1", headers) or {}
        for r in data.get("workflow_runs", [])[:1]:
            runs.append({
                "source": "github", "repo": repo, "name": r.get("name", ""), "branch": r.get("head_branch", ""),
                "status": r.get("conclusion") or r.get("status", ""), "url": r.get("html_url", ""), "updated": r.get("updated_at", ""),
            })
    return items, runs


def _gitea(base: str, token: str, repos: list[str]) -> tuple[list, list]:
    base = base.rstrip("/")
    if "://" not in base:
        base = "https://" + base
    headers = {"Authorization": f"token {token}"}
    items = []
    for kind, typ in (("pr", "pulls"), ("issue", "issues")):
        data = get_json(f"{base}/api/v1/repos/issues/search?state=open&type={typ}&limit=15&{'review_requested=true' if kind == 'pr' else 'assigned=true'}", headers) or []
        mine = get_json(f"{base}/api/v1/repos/issues/search?state=open&type={typ}&limit=15&created=true", headers) or []
        seen = set()
        for it in list(data) + list(mine):
            if it.get("id") in seen:
                continue
            seen.add(it.get("id"))
            items.append({
                "source": "gitea", "kind": kind, "title": it.get("title", ""), "repo": (it.get("repository") or {}).get("full_name", ""),
                "number": it.get("number"), "url": it.get("html_url", ""), "updated": it.get("updated_at", ""),
                "draft": False, "review": it in data and kind == "pr",
            })
    runs = []
    for repo in repos:
        try:
            data = get_json(f"{base}/api/v1/repos/{repo}/actions/tasks?limit=1", headers) or {}
        except Exception:
            continue
        for r in (data.get("workflow_runs") or [])[:1]:
            runs.append({
                "source": "gitea", "repo": repo, "name": r.get("name") or r.get("display_title", ""), "branch": r.get("head_branch", ""),
                "status": r.get("status", ""), "url": r.get("url", "").replace("/api/v1", ""), "updated": r.get("updated_at", ""),
            })
    return items, runs


class DevDash(QObject):
    """Exposed to QML as `DevDash`: `.items` (PRs + issues), `.runs` (CI), `.error`."""

    changed = Signal()
    _ready = Signal("QVariantList", "QVariantList", str)

    def __init__(self):
        super().__init__()
        self._items: list = []
        self._runs: list = []
        self._error = ""
        self._git: dict = {}
        self.repos: list[str] = []
        self._timer = QTimer(self, interval=5 * 60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def configure(self, git: dict):
        if git != self._git:
            self._git = dict(git)
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
        git, repos = dict(self._git), list(self.repos)

        def work():
            items, runs, errors = [], [], []
            source = str(git.get("source") or "github")
            gh_repos = [r.split(":", 1)[1] for r in repos if r.startswith("github:")]
            gt_repos = [r.split(":", 1)[1] for r in repos if r.startswith("gitea:")]
            if source in ("github", "both") and git.get("github_user"):
                try:
                    a, b = _github(str(git["github_user"]), str(git.get("github_token") or ""), gh_repos)
                    items += a
                    runs += b
                except Exception as e:
                    errors.append(f"GitHub: {e}")
            if source in ("gitea", "both") and git.get("gitea_url") and git.get("gitea_token"):
                try:
                    a, b = _gitea(str(git["gitea_url"]), str(git["gitea_token"]), gt_repos)
                    items += a
                    runs += b
                except Exception as e:
                    errors.append(f"Gitea: {e}")
            if not git.get("github_user") and not git.get("gitea_token"):
                errors.append("Add your GitHub or Gitea account in Settings")
            items.sort(key=lambda i: i["updated"], reverse=True)
            self._ready.emit(items, runs, " · ".join(errors))

        threading.Thread(target=work, daemon=True).start()

    @Slot("QVariantList", "QVariantList", str)
    def _on_ready(self, items, runs, error):
        self._items, self._runs, self._error = list(items), list(runs), error
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property("QVariantList", notify=changed)
    def runs(self):
        return self._runs

    @Property(str, notify=changed)
    def error(self):
        return self._error
