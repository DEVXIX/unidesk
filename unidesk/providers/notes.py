"""Notes and to-do lists, one per widget id, saved to ~/.config/unidesk/notes.json."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..config import CONFIG_DIR

STORE = CONFIG_DIR / "notes.json"


class Notes(QObject):
    """Exposed to QML as `Notes`: text(id), setText(id, text), todos(id), addTodo, toggleTodo, removeTodo."""

    changed = Signal(str)  # widget id

    def __init__(self):
        super().__init__()
        try:
            self._data: dict = json.loads(STORE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {}
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save)

    def _save(self):
        try:
            STORE.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _entry(self, widget_id: str) -> dict:
        return self._data.setdefault(widget_id, {"text": "", "todos": []})

    def _touch(self, widget_id: str):
        self.changed.emit(widget_id)
        self._save_timer.start()

    @Slot(str, result=str)
    def text(self, widget_id: str) -> str:
        return self._entry(widget_id)["text"]

    @Slot(str, str)
    def setText(self, widget_id: str, text: str):
        if self._entry(widget_id)["text"] != text:
            self._entry(widget_id)["text"] = text
            self._save_timer.start()

    @Slot(str, result="QVariantList")
    def todos(self, widget_id: str):
        return self._entry(widget_id)["todos"]

    @Slot(str, str)
    def addTodo(self, widget_id: str, text: str):
        if text.strip():
            self._entry(widget_id)["todos"].append({"text": text.strip(), "done": False, "at": time.time()})
            self._touch(widget_id)

    @Slot(str, int)
    def toggleTodo(self, widget_id: str, index: int):
        todos = self._entry(widget_id)["todos"]
        if 0 <= index < len(todos):
            todos[index]["done"] = not todos[index]["done"]
            self._touch(widget_id)

    @Slot(str, int)
    def removeTodo(self, widget_id: str, index: int):
        todos = self._entry(widget_id)["todos"]
        if 0 <= index < len(todos):
            todos.pop(index)
            self._touch(widget_id)

    @Slot(str)
    def clearDone(self, widget_id: str):
        entry = self._entry(widget_id)
        entry["todos"] = [t for t in entry["todos"] if not t["done"]]
        self._touch(widget_id)
