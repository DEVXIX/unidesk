"""Clipboard history: the last things you copied (text, images, files). Kept
in memory only, never written to disk, and emptied when the widget goes.
Copies that password managers mark as private are skipped, the same way
Windows' own clipboard history skips them."""
from __future__ import annotations

import hashlib
import itertools
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QMimeData, QObject, QSize, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage, QImageReader, QPixmap
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

LIMIT = 30          # entries kept
IMAGES = 6          # of which images (full size, in memory)
TEXT_MAX = 200_000  # characters kept per text copy
THUMB = QSize(400, 280)
IMAGE_FILES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".jfif", ".avif", ".heic"}
# Formats that mean "don't record this" (KeePass, 1Password, Bitwarden, browsers' password fields...).
_PRIVATE = ("ExcludeClipboardContentFromMonitorProcessing", "Clipboard Viewer Ignore")
_JUST_A_LINK = re.compile(r"\s*(https?|file|data):\S*\s*")


def _thumbnail(image: QImage) -> QImage:
    if image.width() <= THUMB.width() and image.height() <= THUMB.height():
        return image
    return image.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _file_thumbnail(path: str) -> QImage:
    """A small picture of an image file, decoded at thumbnail size (in the background)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and (size.width() > THUMB.width() or size.height() > THUMB.height()):
        reader.setScaledSize(size.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return image if image.isNull() else _thumbnail(image)


def _private(mime: QMimeData) -> bool:
    for fmt in mime.formats():
        if any(marker in fmt for marker in _PRIVATE):
            return True
        if "CanIncludeInClipboardHistory" in fmt:
            data = bytes(mime.data(fmt))
            if len(data) >= 4 and int.from_bytes(data[:4], "little") == 0:
                return True
    return False


class Clipboard(QObject):
    """Exposed to QML as `Clipboard`: `Clipboard.items` newest first
    ({id, kind: text|image|files, text, detail, at, thumb}), `copy(id)`,
    `remove(id)`, `clear()`, and `copied` (the id just put back, for a moment)."""

    itemsChanged = Signal()
    copiedChanged = Signal()
    _file_thumb_ready = Signal(str, QImage)

    def __init__(self):
        super().__init__()
        self._items: list[dict] = []
        self._payload: dict[str, object] = {}   # id -> full text, QImage or list of paths
        self._thumbs: dict[str, QImage] = {}
        self._ids = itertools.count(1)
        self._running = False
        self._echo = 0.0                        # when we last set the clipboard ourselves
        self._copied = ""
        self.keep_images = True
        self._capture_soon = QTimer(self, singleShot=True, interval=150, timeout=self._capture)
        self._copied_timer = QTimer(self, singleShot=True, interval=1500, timeout=lambda: self._set_copied(""))
        self._file_thumb_ready.connect(self._on_file_thumb)

    def start(self):
        if not self._running:
            self._running = True
            QGuiApplication.clipboard().dataChanged.connect(self._on_change)

    def stop(self):
        if self._running:
            self._running = False
            QGuiApplication.clipboard().dataChanged.disconnect(self._on_change)
            self.clear()

    @Slot()
    def _on_change(self):
        self._capture_soon.start()  # apps often set the clipboard several times in a row

    # ---- recording -------------------------------------------------------------

    def _capture(self):
        if time.monotonic() - self._echo < 1.0:
            return  # our own copy() coming back
        mime = QGuiApplication.clipboard().mimeData()
        if mime is not None:
            self.record(mime)

    def record(self, mime: QMimeData):
        """Add what's in a clipboard snapshot to the history."""
        if _private(mime):
            return
        now = time.time() * 1000
        urls = mime.urls() if mime.hasUrls() else []
        if urls and all(u.isLocalFile() for u in urls):
            self._record_files([u.toLocalFile() for u in urls], now)
            return
        text = mime.text()[:TEXT_MAX] if mime.hasText() else ""
        html = mime.html().lower() if mime.hasHtml() else ""
        # A picture wins over text that only describes it: "Copy image" in a browser
        # adds an <img> tag or the image's link. Text with a rendering of itself
        # attached (Excel, Word) stays text.
        picture = mime.hasImage() and self.keep_images and (not text.strip() or "<img" in html or _JUST_A_LINK.fullmatch(text))
        if picture and self._record_image(mime.imageData(), now):
            return
        if text.strip():
            if self._bump(lambda item: item["kind"] == "text" and self._payload.get(item["id"]) == text, now):
                return
            lines = text.strip().count("\n") + 1
            detail = f"{lines} lines" if lines > 1 else f"{len(text.strip())} characters"
            self._add("text", text, " ".join(text.split())[:300], detail, now)

    def _record_image(self, data, now: float) -> bool:
        image = data.toImage() if isinstance(data, QPixmap) else data
        if not isinstance(image, QImage) or image.isNull():
            image = QGuiApplication.clipboard().image()
        if image.isNull():
            return False
        thumb = _thumbnail(image)
        # Apps often announce the same copy twice (again when they flush the clipboard):
        # recognise a picture by its size and its thumbnail's pixels.
        pixels = bytes(thumb.convertToFormat(QImage.Format.Format_ARGB32).constBits())
        signature = f"{image.width()}x{image.height()}:{hashlib.blake2b(pixels, digest_size=16).hexdigest()}"
        if self._bump(lambda item: item["kind"] == "image" and item.get("signature") == signature, now):
            return True
        item_id = self._add("image", image, f"{image.width()} × {image.height()}", "Image", now, thumb)
        next(i for i in self._items if i["id"] == item_id)["signature"] = signature
        return True

    def _record_files(self, paths: list[str], now: float):
        if self._bump(lambda item: item["kind"] == "files" and self._payload.get(item["id"]) == paths, now):
            return
        names = [Path(p).name or p for p in paths]
        text = names[0] if len(names) == 1 else f"{len(names)} files"
        detail = str(Path(paths[0]).parent) if len(names) == 1 else ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
        item_id = self._add("files", paths, text, detail, now)
        # Copied image files show the first picture.
        picture = next((p for p in paths if Path(p).suffix.lower() in IMAGE_FILES), None)
        if picture and self.keep_images:
            threading.Thread(target=lambda: self._file_thumb_ready.emit(item_id, _file_thumbnail(picture)), daemon=True).start()

    @Slot(str, QImage)
    def _on_file_thumb(self, item_id: str, image: QImage):
        item = next((i for i in self._items if i["id"] == item_id), None)
        if item is None or image.isNull():
            return
        self._thumbs[item_id] = image
        item["thumb"] = f"image://clipboard/{item_id}"
        self.itemsChanged.emit()

    def _bump(self, match, now: float) -> bool:
        """Copied again: move the existing entry to the top."""
        item = next((i for i in self._items if match(i)), None)
        if item is None:
            return False
        self._items.remove(item)
        item["at"] = now
        self._items.insert(0, item)
        self.itemsChanged.emit()
        return True

    def _add(self, kind: str, payload, text: str, detail: str, now: float, thumb: QImage | None = None) -> str:
        item_id = f"c{next(self._ids)}"
        self._payload[item_id] = payload
        if thumb is not None:
            self._thumbs[item_id] = thumb
        self._items.insert(0, {"id": item_id, "kind": kind, "text": text, "detail": detail, "at": now,
                               "thumb": f"image://clipboard/{item_id}" if thumb is not None else ""})
        images = [i for i in self._items if i["kind"] == "image"]
        for old in self._items[LIMIT:] + images[IMAGES:]:
            self._drop(old)
        self.itemsChanged.emit()
        return item_id

    def _drop(self, item: dict):
        if item in self._items:
            self._items.remove(item)
        self._payload.pop(item["id"], None)
        self._thumbs.pop(item["id"], None)

    def thumbnail(self, item_id: str) -> QImage | None:
        return self._thumbs.get(item_id)

    # ---- QML -------------------------------------------------------------------

    @Property("QVariantList", notify=itemsChanged)
    def items(self):
        return self._items

    @Property(str, notify=copiedChanged)
    def copied(self):
        return self._copied

    def _set_copied(self, item_id: str):
        if item_id != self._copied:
            self._copied = item_id
            self.copiedChanged.emit()

    @Slot(str)
    def copy(self, item_id: str):
        """Put an entry back on the clipboard (and move it to the top)."""
        item = next((i for i in self._items if i["id"] == item_id), None)
        payload = self._payload.get(item_id)
        if item is None or payload is None:
            return
        clip = QGuiApplication.clipboard()
        self._echo = time.monotonic()
        if item["kind"] == "image":
            clip.setImage(payload)
        elif item["kind"] == "files":
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(p) for p in payload])
            clip.setMimeData(mime)
        else:
            clip.setText(payload)
        self._bump(lambda i: i is item, time.time() * 1000)
        self._set_copied(item_id)
        self._copied_timer.start()

    @Slot(str)
    def remove(self, item_id: str):
        item = next((i for i in self._items if i["id"] == item_id), None)
        if item is not None:
            self._drop(item)
            self.itemsChanged.emit()

    @Slot()
    def clear(self):
        if self._items:
            self._items, self._payload, self._thumbs = [], {}, {}
            self.itemsChanged.emit()


class ClipboardImages(QQuickImageProvider):
    """image://clipboard/<id>: thumbnails of copied images, straight from memory."""

    def __init__(self, clipboard: Clipboard):
        super().__init__(QQmlImageProviderBase.ImageType.Image)
        self._clipboard = clipboard

    def requestImage(self, image_id, size, requested_size):
        image = self._clipboard.thumbnail(image_id)
        return image if image is not None else QImage()
