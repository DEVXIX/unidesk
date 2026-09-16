"""Share a setup with someone else: export config.yaml without anything
personal, and import one while keeping your own accounts and dock pins."""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from .config import CONFIG_FILE

# Never leaves this PC.
PRIVATE_GIT_KEYS = ("github_user", "github_token", "gitea_url", "gitea_token")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def open_text_file(path: Path):
    """Open in the user's editor; .yaml usually has no app, so fall back to Notepad."""
    try:
        os.startfile(str(path), "edit")
        return
    except OSError:
        pass
    try:
        os.startfile(str(path))
        return
    except OSError:
        pass
    notepad = shutil.which("notepad.exe") or r"C:\Windows\notepad.exe"
    subprocess.Popen([notepad, str(path)])


def export_settings(target: Path) -> list[str]:
    """Write a shareable copy of config.yaml. Returns what was left out."""
    y = _yaml()
    doc = y.load(CONFIG_FILE.read_text(encoding="utf-8"))
    removed = []
    git = (doc.get("settings") or {}).get("git")
    if isinstance(git, dict):
        for key in PRIVATE_GIT_KEYS:
            if git.get(key):
                git[key] = ""
                removed.append(key)
    if (doc.get("settings") or {}).get("github_token"):
        doc["settings"]["github_token"] = ""
        removed.append("github_token")
    dock = doc.get("dock")
    if isinstance(dock, dict) and "pinned" in dock:
        del dock["pinned"]
        removed.append("dock pins")
    for w in doc.get("widgets") or []:
        opts = w.get("options") if isinstance(w, dict) else None
        if not isinstance(opts, dict):
            continue
        for key in ("src", "avatar", "background"):
            value = str(opts.get(key) or "")
            if value and value not in ("wallpaper", "artwork", "github") and (":" in value or value.startswith(("~", "/", "\\"))):
                opts[key] = "wallpaper" if key != "avatar" else "github"
                removed.append(f"{w.get('id')} {key} (a file on this PC)")
    out = StringIO()
    y.dump(doc, out)
    target.write_text(out.getvalue(), encoding="utf-8")
    return removed


def import_settings(source: Path) -> None:
    """Replace config.yaml with a shared one, keeping this PC's accounts and dock pins."""
    y = _yaml()
    incoming = y.load(source.read_text(encoding="utf-8"))
    if not isinstance(incoming, dict) or "widgets" not in incoming:
        raise ValueError("that file doesn't look like unidesk settings")
    mine = y.load(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}

    my_git = ((mine or {}).get("settings") or {}).get("git")
    if isinstance(my_git, dict):
        incoming.setdefault("settings", {})
        git = incoming["settings"].get("git")
        if not isinstance(git, dict):
            incoming["settings"]["git"] = copy.deepcopy(my_git)
        else:
            for key in PRIVATE_GIT_KEYS + ("source", "profile"):
                if key in my_git:
                    git[key] = my_git[key]
    my_pins = ((mine or {}).get("dock") or {}).get("pinned")
    if my_pins is not None:
        incoming.setdefault("dock", {})
        incoming["dock"]["pinned"] = my_pins

    backup = CONFIG_FILE.with_suffix(".before-import.yaml")
    if CONFIG_FILE.exists():
        shutil.copyfile(CONFIG_FILE, backup)
    out = StringIO()
    y.dump(incoming, out)
    CONFIG_FILE.write_text(out.getvalue(), encoding="utf-8")
