"""Alle Symbole werden zur Laufzeit gezeichnet – keine Icon-Theme-Abhängigkeit."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_CACHE: dict[tuple, QIcon] = {}


def icon(name: str, color: str = "#e8e8ec", size: int = 22) -> QIcon:
    key = (name, color, size)
    if key not in _CACHE:
        _CACHE[key] = _make(name, color, size)
    return _CACHE[key]


def app_icon() -> QIcon:
    """The application icon (SVG shipped with the package); falls back to a drawn one."""
    if "app_svg" not in _CACHE:
        svg = Path(__file__).parent / "data" / "ksnapmark.svg"
        themed = QIcon(str(svg)) if svg.exists() else QIcon()
        _CACHE["app_svg"] = themed if not themed.isNull() else icon("app", "#4ea1ff", 64)
    return _CACHE["app_svg"]


def _make(name: str, color: str, size: int) -> QIcon:
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    col = QColor(color)
    pen = QPen(col, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _DRAW.get(name, _draw_missing)(p, col)
    p.end()
    return QIcon(pm)


def _poly(*pts: tuple[float, float]) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _fill(col: QColor, alpha: int = 255) -> QColor:
    c = QColor(col)
    c.setAlpha(alpha)
    return c


def _draw_missing(p, col):
    p.drawRect(QRectF(5, 5, 14, 14))


def _pen(p, col):
    p.drawPolygon(_poly((4, 20), (5, 15), (15, 5), (19, 9), (9, 19)))
    p.drawLine(QPointF(13, 7), QPointF(17, 11))


def _marker(p, col):
    p.setBrush(_fill(col, 110))
    p.drawPolygon(_poly((5, 15), (13, 7), (18, 12), (10, 20)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(4, 21), QPointF(11, 21))


def _arrow(p, col):
    p.drawLine(QPointF(5, 19), QPointF(16, 8))
    p.setBrush(col)
    p.drawPolygon(_poly((20, 4), (11.5, 6), (18, 12.5)))


def _line(p, col):
    p.drawLine(QPointF(5, 19), QPointF(19, 5))


def _rect(p, col):
    p.drawRoundedRect(QRectF(4, 6, 16, 12), 1.5, 1.5)


def _ellipse(p, col):
    p.drawEllipse(QRectF(4, 5, 16, 14))


def _text(p, col):
    p.drawLine(QPointF(6, 6), QPointF(18, 6))
    p.drawLine(QPointF(12, 6), QPointF(12, 19))
    p.drawLine(QPointF(9.5, 19), QPointF(14.5, 19))


def _number(p, col):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    p.drawLine(QPointF(10.5, 9.5), QPointF(12.5, 8))
    p.drawLine(QPointF(12.5, 8), QPointF(12.5, 16))


def _blur(p, col):
    p.setPen(Qt.PenStyle.NoPen)
    for ix, x in enumerate((6, 12, 18)):
        for iy, y in enumerate((6, 12, 18)):
            a = 255 - (ix + iy) * 55
            p.setBrush(_fill(col, max(40, a)))
            p.drawEllipse(QPointF(x, y), 2.3, 2.3)


def _pixel(p, col):
    p.setPen(Qt.PenStyle.NoPen)
    alphas = [255, 150, 220, 120, 255, 90, 200, 140, 255]
    i = 0
    for y in (3.5, 9.5, 15.5):
        for x in (3.5, 9.5, 15.5):
            p.setBrush(_fill(col, alphas[i]))
            p.drawRect(QRectF(x, y, 5, 5))
            i += 1


def _redact(p, col):
    p.setBrush(col)
    p.drawRoundedRect(QRectF(3, 8, 18, 8), 1.5, 1.5)


def _spot(p, col):
    p.setBrush(_fill(col, 60))
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 2, 2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(8, 8, 8, 8))


def _frame(p, col):
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 3, 3)
    p.setBrush(_fill(col, 110))
    p.drawRoundedRect(QRectF(7, 7, 10, 10), 1.5, 1.5)


def _crop(p, col):
    p.drawPolyline(_poly((7, 3), (7, 17), (21, 17)))
    p.drawPolyline(_poly((3, 7), (17, 7), (17, 21)))


def _undo(p, col):
    p.drawPolyline(_poly((8, 5), (4, 9), (8, 13)))
    path = QPainterPath(QPointF(4, 9))
    path.lineTo(14, 9)
    path.cubicTo(20, 9, 20, 19, 14, 19)
    path.lineTo(8, 19)
    p.drawPath(path)


def _redo(p, col):
    p.translate(24, 0)
    p.scale(-1, 1)
    _undo(p, col)


def _copy(p, col):
    p.drawRoundedRect(QRectF(4, 4, 11, 11), 1.5, 1.5)
    p.drawRoundedRect(QRectF(9, 9, 11, 11), 1.5, 1.5)


def _save(p, col):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 1.5, 1.5)
    p.drawRect(QRectF(8, 4, 8, 5))
    p.drawRect(QRectF(7.5, 13, 9, 7))


def _share(p, col):
    p.drawLine(QPointF(8, 11), QPointF(16, 6.5))
    p.drawLine(QPointF(8, 13), QPointF(16, 17.5))
    p.setBrush(col)
    for x, y in ((18, 5.5), (6, 12), (18, 18.5)):
        p.drawEllipse(QPointF(x, y), 2.6, 2.6)


def _ocr(p, col):
    for pts in (((3, 8), (3, 3), (8, 3)), ((16, 3), (21, 3), (21, 8)),
                ((3, 16), (3, 21), (8, 21)), ((21, 16), (21, 21), (16, 21))):
        p.drawPolyline(_poly(*pts))
    p.drawLine(QPointF(7, 9), QPointF(17, 9))
    p.drawLine(QPointF(7, 12.5), QPointF(17, 12.5))
    p.drawLine(QPointF(7, 16), QPointF(13, 16))


def _idea(p, col):
    p.drawEllipse(QRectF(6.5, 2.5, 11, 11))
    p.drawLine(QPointF(9, 16.5), QPointF(15, 16.5))
    p.drawLine(QPointF(10, 20), QPointF(14, 20))
    p.drawLine(QPointF(10.5, 13.5), QPointF(10.5, 16.5))
    p.drawLine(QPointF(13.5, 13.5), QPointF(13.5, 16.5))


def _close(p, col):
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _wand(p, col):
    p.drawLine(QPointF(12, 3), QPointF(12, 21))
    p.drawLine(QPointF(3, 12), QPointF(21, 12))
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _app(p, col):
    p.setBrush(_fill(col, 40))
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 4, 4)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(_poly((8, 6), (6, 6), (6, 8)))
    p.drawPolyline(_poly((16, 6), (18, 6), (18, 8)))
    p.drawPolyline(_poly((8, 18), (6, 18), (6, 16)))
    p.drawPolyline(_poly((16, 18), (18, 18), (18, 16)))
    p.setBrush(col)
    p.drawEllipse(QPointF(12, 12), 2.2, 2.2)


def _folder(p, col):
    p.drawPolygon(_poly((3, 7), (9, 7), (11, 9), (21, 9), (21, 19), (3, 19)))


def _trash(p, col):
    p.drawLine(QPointF(5, 7), QPointF(19, 7))
    p.drawRect(QRectF(8, 4, 8, 3))
    p.drawPolygon(_poly((6.5, 7), (17.5, 7), (16.5, 20), (7.5, 20)))


def _pick(p, col):
    p.drawPolygon(_poly((14, 6), (18, 10), (9, 19), (5, 19), (5, 15)))
    p.drawLine(QPointF(12, 8), QPointF(16, 12))
    p.drawLine(QPointF(15, 5), QPointF(19, 9))


def _select(p, col):
    p.setBrush(col)
    p.drawPolygon(_poly((6, 4), (6, 18), (10, 14), (13, 20), (15.5, 19), (12.5, 13), (18, 13)))


def _qr(p, col):
    for x, y in ((4, 4), (14, 4), (4, 14)):
        p.drawRect(QRectF(x, y, 6, 6))
        p.fillRect(QRectF(x + 2, y + 2, 2, 2), col)
    p.fillRect(QRectF(14, 14, 3, 3), col)
    p.fillRect(QRectF(18, 17, 3, 3), col)
    p.fillRect(QRectF(14, 19, 2, 2), col)


def _pin(p, col):
    p.drawPolygon(_poly((9, 4), (16, 4), (15, 11), (18, 14), (6, 14), (9, 11)))
    p.drawLine(QPointF(12, 14), QPointF(12, 21))


def _settings(p, col):
    p.drawEllipse(QRectF(9, 9, 6, 6))
    for ang in range(0, 360, 45):
        p.save()
        p.translate(12, 12)
        p.rotate(ang)
        p.drawLine(QPointF(0, -7), QPointF(0, -10))
        p.restore()
    p.drawEllipse(QRectF(6, 6, 12, 12))


_DRAW = {
    "select": _select, "pick": _pick, "qr": _qr, "pin": _pin, "settings": _settings,
    "pen": _pen, "marker": _marker, "arrow": _arrow, "line": _line, "rect": _rect,
    "ellipse": _ellipse, "text": _text, "number": _number, "blur": _blur,
    "pixel": _pixel, "redact": _redact, "spot": _spot, "frame": _frame, "crop": _crop, "undo": _undo, "redo": _redo,
    "copy": _copy, "save": _save, "share": _share, "ocr": _ocr, "idea": _idea,
    "close": _close, "wand": _wand, "app": _app, "folder": _folder, "trash": _trash,
}

ICON_SIZE = QSize(22, 22)
