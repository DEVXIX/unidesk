"""Where a widget sits on its screen: an anchor (the corner, edge or centre it
sticks to) plus x / y offsets measured inward from there. A widget near the
right edge keeps its distance from the right edge on a wider monitor, one in
the middle stays in the middle, and so on.

QML mirrors position() in WidgetFrame.qml."""
from __future__ import annotations

import math

ANCHORS =("top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right")
DEFAULT = "top-left"

_ALIASES = {
    "centre": "center", "middle": "center", "center-center": "center", "middle-center": "center",
    "top-center": "top", "center-top": "top", "top-middle": "top",
    "bottom-center": "bottom", "center-bottom": "bottom", "bottom-middle": "bottom",
    "center-left": "left", "middle-left": "left", "left-center": "left",
    "center-right": "right", "middle-right": "right", "right-center": "right",
    "left-top": "top-left", "right-top": "top-right", "left-bottom": "bottom-left", "right-bottom": "bottom-right",
}


def normalize(name) -> str:
    key = str(name or "").strip().lower().replace("_", "-").replace(" ", "-")
    key = _ALIASES.get(key, key)
    return key if key in ANCHORS else DEFAULT


def split(anchor) -> tuple[str, str]:
    """-> (left | center | right, top | middle | bottom)"""
    a = normalize(anchor)
    horizontal = "left" if a.endswith("left") else "right" if a.endswith("right") else "center"
    vertical = "top" if a.startswith("top") else "bottom" if a.startswith("bottom") else "middle"
    return horizontal, vertical


def join(horizontal: str, vertical: str) -> str:
    if vertical == "middle":
        return "center" if horizontal == "center" else horizontal
    if horizontal == "center":
        return vertical
    return f"{vertical}-{horizontal}"


def nearest(left: float, top: float, width: float, height: float, area_w: float, area_h: float) -> str:
    """The anchor for a widget dropped here: whichever third of the screen its centre is in."""
    cx, cy = left + width / 2, top + height / 2
    horizontal = "left" if cx < area_w / 3 else "right" if cx > area_w * 2 / 3 else "center"
    vertical = "top" if cy < area_h / 3 else "bottom" if cy > area_h * 2 / 3 else "middle"
    return join(horizontal, vertical)


def offsets(anchor, left: float, top: float, width: float, height: float, area_w: float, area_h: float) -> tuple[int, int]:
    """Top-left position -> x / y from the anchor. Centred placements can land on
    half pixels; flooring makes QML's Math.round (halves up) give back `left` / `top`."""
    left, top = math.floor(left + 0.5), math.floor(top + 0.5)
    horizontal, vertical = split(anchor)
    if horizontal == "left":
        x = left
    elif horizontal == "right":
        x = area_w - width - left
    else:
        x = left + width / 2 - area_w / 2
    if vertical == "top":
        y = top
    elif vertical == "bottom":
        y = area_h - height - top
    else:
        y = top + height / 2 - area_h / 2
    return math.floor(x + 1e-9), math.floor(y + 1e-9)


def position(anchor, x: float, y: float, width: float, height: float, area_w: float, area_h: float) -> tuple[float, float]:
    """x / y from the anchor -> top-left position (the inverse of offsets)."""
    horizontal, vertical = split(anchor)
    left = x if horizontal == "left" else area_w - width - x if horizontal == "right" else (area_w - width) / 2 + x
    top = y if vertical == "top" else area_h - height - y if vertical == "bottom" else (area_h - height) / 2 + y
    return left, top
