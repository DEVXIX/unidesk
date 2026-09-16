"""Material You colours: a seed from the album art, the wallpaper or a fixed
colour, turned into the Material 3 roles (primary, surfaceContainer, ...)."""
from __future__ import annotations

import threading

from materialyoucolor.dynamiccolor.material_dynamic_colors import COLOR_NAMES, MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.quantize import QuantizeCelebi
from materialyoucolor.scheme.scheme_content import SchemeContent
from materialyoucolor.scheme.scheme_expressive import SchemeExpressive
from materialyoucolor.scheme.scheme_fidelity import SchemeFidelity
from materialyoucolor.scheme.scheme_neutral import SchemeNeutral
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot
from materialyoucolor.scheme.scheme_vibrant import SchemeVibrant
from materialyoucolor.score.score import Score
from PySide6.QtCore import Property, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader

SCHEMES = {
    "tonal-spot": SchemeTonalSpot,
    "vibrant": SchemeVibrant,
    "expressive": SchemeExpressive,
    "fidelity": SchemeFidelity,
    "content": SchemeContent,
    "neutral": SchemeNeutral,
}

_DYNAMIC = MaterialDynamicColors()
_seed_cache: dict[str, int] = {}


def seed_from_image(path: str) -> int | None:
    if path in _seed_cache:
        return _seed_cache[path]
    # Decode straight to a thumbnail; a 4K wallpaper would otherwise take ~30 MB.
    reader = QImageReader(path)
    reader.setScaledSize(QSize(96, 96))
    image = reader.read()
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(image.constBits())
    pixels = [[data[i], data[i + 1], data[i + 2], data[i + 3]] for i in range(0, len(data), 4)]
    ranked = Score.score(QuantizeCelebi(pixels, 128))
    seed = ranked[0] if ranked else None
    if seed is not None:
        if len(_seed_cache) > 64:
            _seed_cache.pop(next(iter(_seed_cache)))
        _seed_cache[path] = seed
    return seed


def scheme_colors(seed: int, dark: bool, variant: str) -> dict[str, str]:
    scheme = SCHEMES.get(variant, SchemeTonalSpot)(Hct.from_int(seed), dark, 0.0)
    out = {}
    for name in COLOR_NAMES:
        color = getattr(_DYNAMIC, name, None)
        if color is None:
            continue
        argb = color.get_argb(scheme)
        out[name] = f"#{argb & 0xFFFFFF:06x}"
    return out


def _hex_to_argb(value: str) -> int:
    value = str(value).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return 0xFF000000 | int(value[:6], 16)
    except ValueError:
        return 0xFFB5485D


class Theme(QObject):
    """Exposed to QML as `Theme`: `Theme.c.primary`, `Theme.font`, `Theme.radius`..."""

    colorsChanged = Signal()
    styleChanged = Signal()
    _computed = Signal(str, "QVariantMap")

    def __init__(self, font_family: str, icon_family: str):
        super().__init__()
        self._colors = scheme_colors(_hex_to_argb("#b5485d"), True, "tonal-spot")
        self._style: dict = {}
        self._font = font_family
        self._icon_font = icon_family
        self._settings: dict = {}
        self._art: str | None = None
        self._wallpaper: str | None = None
        self._key = ""
        self._computed.connect(self._apply, Qt.ConnectionType.QueuedConnection)

    # ---- inputs ----------------------------------------------------------------

    def configure(self, theme: dict, style: dict):
        self._settings = theme or {}
        if style != self._style:
            self._style = style or {}
            self.styleChanged.emit()
        self._recompute()

    def set_art(self, path: str | None):
        self._art = path
        if self._settings.get("source", "artwork") == "artwork":
            self._recompute()

    def set_wallpaper(self, path: str | None):
        self._wallpaper = path
        self._recompute()

    # ---- computing -------------------------------------------------------------

    def _recompute(self):
        source = self._settings.get("source", "artwork")
        dark = self._settings.get("mode", "dark") != "light"
        variant = self._settings.get("scheme", "tonal-spot")
        fallback = _hex_to_argb(self._settings.get("color", "#b5485d"))
        image = None
        if source == "artwork":
            image = self._art or self._wallpaper
        elif source == "wallpaper":
            image = self._wallpaper
        key = f"{image}|{dark}|{variant}|{fallback}"
        if key == self._key:
            return
        self._key = key

        def work():
            seed = (seed_from_image(image) if image else None) or fallback
            self._computed.emit(key, scheme_colors(seed, dark, variant))

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, "QVariantMap")
    def _apply(self, key: str, colors: dict):
        if key != self._key:
            return  # a newer request is on its way
        self._colors = colors
        self.colorsChanged.emit()

    # ---- QML -------------------------------------------------------------------

    @Property("QVariantMap", notify=colorsChanged)
    def c(self):
        return self._colors

    @Property(bool, notify=colorsChanged)
    def dark(self):
        return self._settings.get("mode", "dark") != "light"

    @Property(str, notify=styleChanged)
    def font(self):
        return str(self._style.get("font") or self._font)

    @Property(str, constant=True)
    def iconFont(self):
        return self._icon_font

    @Property(float, notify=styleChanged)
    def radius(self):
        return float(self._style.get("radius", 28))

    @Property(float, notify=styleChanged)
    def cardOpacity(self):
        return float(self._style.get("card_opacity", 0.9))

    @Property(float, notify=styleChanged)
    def roundness(self):
        """Google Sans Flex ROND axis, 0..100."""
        return float(self._style.get("font_roundness", 60))

    @Property(bool, notify=styleChanged)
    def shadows(self):
        return bool(self._style.get("shadows", True))

    @Property(float, notify=styleChanged)
    def scale(self):
        try:
            return min(4.0, max(0.25, float(self._style.get("scale", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    @Property(float, notify=styleChanged)
    def animationSpeed(self):
        return float(self._style.get("animation_speed", 1.0))
