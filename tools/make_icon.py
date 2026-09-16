"""Draw the app icon (a Material cookie with the 2x2 tile mark) -> build/unidesk.ico."""
import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

OUT = Path(__file__).resolve().parents[1] / "build" / "unidesk.ico"


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    c = size / 2
    cookie = QPainterPath()
    for i in range(241):
        t = i / 240 * math.tau
        r = c * (1 - 0.07 + 0.07 * math.cos(9 * t)) * 0.98
        point = QPointF(c + r * math.sin(t), c - r * math.cos(t))
        cookie.moveTo(point) if i == 0 else cookie.lineTo(point)
    p.fillPath(cookie, QColor("#ffb1c1"))

    tile = size * 0.2
    gap = size * 0.06
    start = c - tile - gap / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#5e1130"))
    for dx in (0, 1):
        for dy in (0, 1):
            p.drawRoundedRect(start + dx * (tile + gap), start + dy * (tile + gap), tile, tile, tile * 0.3, tile * 0.3)
    p.end()
    return image


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    render(256).save(str(OUT))
    render(256).save(str(OUT.with_suffix(".png")))
    print(OUT)
