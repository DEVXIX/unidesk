"""~/.config/unidesk/config.yaml: created on first run, watched for edits,
and updated in place (comments kept) when a widget is dragged somewhere new."""
from __future__ import annotations

import copy
import os
from io import StringIO
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

CONFIG_DIR = Path(os.environ["UNIDESK_HOME"]) if os.environ.get("UNIDESK_HOME") else Path.home() / ".config" / "unidesk"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEFAULT_FILE = Path(__file__).parent / "defaults" / "config.yaml"


def _plain(value):
    """ruamel's commented maps/lists -> plain dicts/lists for QML."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    # ruamel wraps scalars (ScalarFloat, ScalarBoolean, ...); Qt only knows the builtins.
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return value


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigStore(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.width = 4096
        self.defaults = _plain(self._yaml.load(DEFAULT_FILE.read_text(encoding="utf-8")))
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            CONFIG_FILE.write_text(DEFAULT_FILE.read_text(encoding="utf-8"), encoding="utf-8")

        self.config: dict = self.defaults
        self.error: str | None = None
        self._last_text = ""
        self._load()

        self._debounce = QTimer(self, singleShot=True, interval=150, timeout=self._reload_if_changed)
        self._watcher = QFileSystemWatcher([str(CONFIG_FILE)], self)
        self._watcher.fileChanged.connect(lambda _: self._debounce.start())

    # ---- reading ---------------------------------------------------------------

    def _load(self):
        text = CONFIG_FILE.read_text(encoding="utf-8")
        self._last_text = text
        try:
            raw = _plain(self._yaml.load(text)) or {}
        except YAMLError as e:
            # Keep the last good layout while the file is mid-edit.
            mark = getattr(e, "problem_mark", None)
            where = f" (line {mark.line + 1})" if mark else ""
            self.error = f"config.yaml{where}: {getattr(e, 'problem', None) or e}"
            return
        self.error = None
        merged = _merge({k: v for k, v in self.defaults.items() if k != "widgets"}, raw)
        widgets = raw.get("widgets") if isinstance(raw.get("widgets"), list) else []
        merged["widgets"] = [
            {**w, "x": _num(w.get("x")), "y": _num(w.get("y")), "scale": _scale(w.get("scale")), "options": w.get("options") or {}}
            for w in widgets
            if isinstance(w, dict) and w.get("id") and w.get("type")
        ]
        self.config = merged

    def _reload_if_changed(self):
        # Editors often replace the file, which drops it from the watcher.
        if str(CONFIG_FILE) not in self._watcher.files() and CONFIG_FILE.exists():
            self._watcher.addPath(str(CONFIG_FILE))
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
        except OSError:
            return
        if text == self._last_text:
            return
        self._load()
        self.changed.emit()

    # ---- writing ---------------------------------------------------------------
    # All edits go through ruamel's round-trip document so comments survive.

    def _edit(self, change) -> bool:
        doc = self._yaml.load(CONFIG_FILE.read_text(encoding="utf-8"))
        if doc.get("widgets") is None:
            doc["widgets"] = []
        if change(doc) is False:
            return False
        out = StringIO()
        self._yaml.dump(doc, out)
        CONFIG_FILE.write_text(out.getvalue(), encoding="utf-8")
        self._load()
        return True

    @staticmethod
    def _find(doc, widget_id: str):
        for item in doc["widgets"]:
            if isinstance(item, dict) and item.get("id") == widget_id:
                return item
        return None

    def place_widget(self, widget_id: str, x: int, y: int, scale: float | None = None):
        """Position (and size) from edit mode. No change signal: the widget is already there."""
        def change(doc):
            item = self._find(doc, widget_id)
            if item is None:
                return False
            item["x"], item["y"] = int(x), int(y)
            if scale is not None:
                value = round(float(scale), 2)
                if "scale" in item:
                    item["scale"] = value
                elif value != 1:
                    item.insert(list(item.keys()).index("y") + 1, "scale", value)
        self._edit(change)

    def set_option(self, widget_id: str, key: str, value):
        def change(doc):
            item = self._find(doc, widget_id)
            if item is None:
                return False
            if key == "scale":
                item["scale"] = round(float(value), 2)
                return
            if not isinstance(item.get("options"), dict):
                item["options"] = {}
            item["options"][key] = value
        if self._edit(change):
            self.changed.emit()

    def set_setting(self, path: str, value):
        """theme.source, style.radius, settings.git.gitea_url, ..."""
        from ruamel.yaml.comments import CommentedMap

        keys = [k for k in str(path).split(".") if k]
        if not keys or keys[0] not in ("theme", "style", "settings", "dock", "search"):
            return

        def change(doc):
            node = doc
            for key in keys[:-1]:
                if not isinstance(node.get(key), dict):
                    node[key] = CommentedMap()
                node = node[key]
            node[keys[-1]] = value
        if self._edit(change):
            self.changed.emit()

    def add_widget(self, widget_type: str, x: int, y: int) -> str:
        taken = {w["id"] for w in self.config["widgets"]}
        widget_id, n = widget_type, 2
        while widget_id in taken:
            widget_id, n = f"{widget_type}-{n}", n + 1

        def change(doc):
            doc["widgets"].append({"id": widget_id, "type": widget_type, "x": int(x), "y": int(y), "options": {}})
        if self._edit(change):
            self.changed.emit()
        return widget_id

    def remove_widget(self, widget_id: str):
        def change(doc):
            item = self._find(doc, widget_id)
            if item is None:
                return False
            doc["widgets"].remove(item)
        if self._edit(change):
            self.changed.emit()


def _num(value) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _scale(value) -> float:
    try:
        return min(4.0, max(0.25, float(value)))
    except (TypeError, ValueError):
        return 1.0
