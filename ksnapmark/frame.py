"""Frame, background and shadow around a screenshot (for presentations, blog posts, social media)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath

from .i18n import tr

# key -> (label, start color, end color or None for a flat color, None = transparent)
BACKGROUNDS = {
    "ocean": (tr("Ocean"), "#4facfe", "#00f2fe"),
    "sunset": (tr("Sunset"), "#ff9a9e", "#fad0c4"),
    "violet": (tr("Violet"), "#7f5af0", "#2cb1ff"),
    "dark": (tr("Dark"), "#1e1f26", None),
    "white": (tr("White"), "#ffffff", None),
    "transparent": (tr("Transparent"), None, None),
}


def add_frame(img: QImage, padding: int = 48, background: str = "ocean", radius: int = 12,
              shadow: bool = True) -> QImage:
    """Return ``img`` on a colored/gradient background with rounded corners and a soft shadow."""
    padding = max(0, int(padding))
    radius = max(0, int(radius))
    w, h = img.width(), img.height()
    W, H = w + 2 * padding, h + 2 * padding
    out = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

    _label, c1, c2 = BACKGROUNDS.get(background, BACKGROUNDS["ocean"])
    if c1 is not None and padding > 0:
        if c2 is None:
            p.fillRect(QRectF(0, 0, W, H), QColor(c1))
        else:
            grad = QLinearGradient(QPointF(0, 0), QPointF(W, H))
            grad.setColorAt(0.0, QColor(c1))
            grad.setColorAt(1.0, QColor(c2))
            p.fillRect(QRectF(0, 0, W, H), grad)

    inner = QRectF(padding, padding, w, h)
    if shadow and padding >= 8:
        f = max(3, padding // 4)                      # blur by drawing small and scaling up smoothly
        small = QImage(max(1, W // f), max(1, H // f), QImage.Format.Format_ARGB32_Premultiplied)
        small.fill(Qt.GlobalColor.transparent)
        sx, sy = small.width() / W, small.height() / H
        sp = QPainter(small)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setPen(Qt.PenStyle.NoPen)
        sp.setBrush(QColor(0, 0, 0, 95))
        off = padding * 0.22
        sp.drawRoundedRect(QRectF(padding * sx, (padding + off) * sy, w * sx, h * sy), radius * sx, radius * sy)
        sp.end()
        p.drawImage(QRectF(0, 0, W, H), small)
    path = QPainterPath()
    path.addRoundedRect(inner, radius, radius)
    p.setClipPath(path)
    p.drawImage(inner.topLeft(), img)
    p.end()
    return out
