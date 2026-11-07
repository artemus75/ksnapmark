"""Zeichen-Elemente und ihr Rendering.

Alle Koordinaten sind Bildpixel. Effekte (Blur, Mosaik, Schwärzen) werden beim
Rendern direkt in die Pixel gerechnet – beim Speichern/Kopieren bleibt also
nichts Verdecktes im Bild zurück.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen,
                           QPolygonF)

EFFECT_KINDS = {"blur", "pixel", "redact", "spot"}
SPOT_DIM = 150   # alpha of the darkening outside a spotlight


@dataclass
class Item:
    kind: str
    color: str = "#ff2d2d"
    width: float = 6.0
    p1: QPointF = field(default_factory=QPointF)
    p2: QPointF = field(default_factory=QPointF)
    points: list = field(default_factory=list)
    text: str = ""
    number: int = 0
    filled: bool = False
    unit: float = 1.0

    def rect(self) -> QRectF:
        return QRectF(self.p1, self.p2).normalized()


def _hints(p: QPainter) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)


def render(base: QImage, items: list[Item]) -> QImage:
    """Bild + alle Elemente zu einem flachen Bild verrechnen."""
    img = base.copy().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if not items:
        return img
    p = QPainter(img)
    _hints(p)
    for it in items:
        if it.kind in EFFECT_KINDS:
            p.end()
            _apply_effect(img, it)
            p = QPainter(img)
            _hints(p)
        else:
            draw_item(p, it)
    p.end()
    return img


def _apply_effect(img: QImage, it: Item) -> None:
    r = it.rect().toAlignedRect().intersected(img.rect())
    if r.width() < 2 or r.height() < 2:
        return
    if it.kind == "spot":
        outside = QPainterPath()
        outside.addRect(QRectF(img.rect()))
        hole = QPainterPath()
        hole.addRect(QRectF(r))
        p = QPainter(img)
        p.fillPath(outside.subtracted(hole), QColor(0, 0, 0, SPOT_DIM))
        p.end()
        return
    if it.kind == "redact":
        p = QPainter(img)
        p.fillRect(r, QColor("#000000"))
        p.end()
        return
    block = max(4, int(it.width * 2))
    region = img.copy(r)
    sw = max(1, r.width() // block)
    sh = max(1, r.height() // block)
    small = region.scaled(sw, sh, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    mode = (Qt.TransformationMode.SmoothTransformation if it.kind == "blur"
            else Qt.TransformationMode.FastTransformation)
    out = small.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio, mode)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    p.drawImage(r.topLeft(), out)
    p.end()


def text_px(it: Item) -> float:
    return max(10.0, it.width * 2.0 + 10.0 * it.unit)


def _freehand_path(points: list) -> QPainterPath:
    path = QPainterPath(points[0])
    if len(points) == 2:
        path.lineTo(points[1])
        return path
    for i in range(1, len(points)):
        mid = QPointF((points[i - 1].x() + points[i].x()) / 2,
                      (points[i - 1].y() + points[i].y()) / 2)
        path.quadTo(points[i - 1], mid)
    path.lineTo(points[-1])
    return path


def draw_item(p: QPainter, it: Item) -> None:
    col = QColor(it.color)
    k = it.kind
    p.save()
    try:
        if k in ("pen", "marker"):
            if not it.points:
                return
            c = QColor(col)
            w = it.width
            cap = Qt.PenCapStyle.RoundCap
            if k == "marker":
                c.setAlpha(105)
                w = it.width * 3.2
                cap = Qt.PenCapStyle.SquareCap
            pen = QPen(c, w, Qt.PenStyle.SolidLine, cap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if len(it.points) == 1:
                p.drawPoint(it.points[0])
            else:
                p.drawPath(_freehand_path(it.points))
        elif k == "line":
            p.setPen(QPen(col, it.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(it.p1, it.p2)
        elif k == "arrow":
            _draw_arrow(p, it, col)
        elif k in ("rect", "ellipse"):
            p.setPen(QPen(col, it.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(col if it.filled else Qt.BrushStyle.NoBrush)
            r = it.rect()
            if k == "rect":
                p.drawRect(r)
            else:
                p.drawEllipse(r)
        elif k == "text":
            font = QFont()
            font.setPixelSize(int(text_px(it)))
            p.setFont(font)
            p.setPen(col)
            flags = (Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignTop.value
                     | Qt.TextFlag.TextDontClip.value)
            p.drawText(QRectF(it.p1, QSizeF(6000, 6000)), flags, it.text)
        elif k == "number":
            r = it.width * 1.6 + 8.0 * it.unit
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(it.p1, r, r)
            font = QFont()
            font.setBold(True)
            font.setPixelSize(max(8, int(r * 1.15)))
            p.setFont(font)
            lum = 0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue()
            p.setPen(QColor("#000000") if lum > 160 else QColor("#ffffff"))
            p.drawText(QRectF(it.p1.x() - r, it.p1.y() - r, 2 * r, 2 * r),
                       Qt.AlignmentFlag.AlignCenter.value, str(it.number))
    finally:
        p.restore()


def _draw_arrow(p: QPainter, it: Item, col: QColor) -> None:
    dx = it.p2.x() - it.p1.x()
    dy = it.p2.y() - it.p1.y()
    length = math.hypot(dx, dy)
    if length < 2:
        return
    a = math.atan2(dy, dx)
    ca, sa = math.cos(a), math.sin(a)
    head_len = min(max(it.width * 3.5, 12.0 * it.unit), length)
    head_w = head_len * 0.9
    base = QPointF(it.p2.x() - head_len * ca, it.p2.y() - head_len * sa)
    left = QPointF(base.x() - sa * head_w / 2, base.y() + ca * head_w / 2)
    right = QPointF(base.x() + sa * head_w / 2, base.y() - ca * head_w / 2)
    shaft_end = QPointF(base.x() + 0.3 * head_len * ca, base.y() + 0.3 * head_len * sa)
    if length > head_len:
        p.setPen(QPen(col, it.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(it.p1, shaft_end)
    p.setPen(QPen(col, max(1.0, it.width * 0.25), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(col)
    p.drawPolygon(QPolygonF([it.p2, left, right]))


def draw_preview(p: QPainter, it: Item, bounds: QRectF) -> None:
    """Vorschau während des Ziehens (Effekte nur als Rahmen)."""
    if it.kind in EFFECT_KINDS or it.kind == "crop":
        r = it.rect()
        p.save()
        if it.kind in ("crop", "spot"):
            outside = QPainterPath()
            outside.addRect(bounds)
            hole = QPainterPath()
            hole.addRect(r)
            p.fillPath(outside.subtracted(hole), QColor(0, 0, 0, 120 if it.kind == "crop" else SPOT_DIM))
            pen = QPen(QColor("#ffffff"), max(1.0, it.unit), Qt.PenStyle.DashLine)
        else:
            fill = {"redact": QColor(0, 0, 0, 170), "blur": QColor(255, 255, 255, 70),
                    "pixel": QColor(255, 255, 255, 70)}[it.kind]
            p.fillRect(r, fill)
            pen = QPen(QColor("#ffffff"), max(1.0, it.unit), Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.restore()
    else:
        draw_item(p, it)


# --- Auswahl: Geometrie der Elemente ---------------------------------------------------------

BOX_ITEMS = ("rect", "ellipse", "blur", "pixel", "redact", "spot")
LINE_ITEMS = ("line", "arrow")


def clone(it: Item) -> Item:
    """Unabhängige Kopie (Undo-Schritte teilen sich Element-Objekte und dürfen nie verändert werden)."""
    return replace(it, p1=QPointF(it.p1), p2=QPointF(it.p2), points=[QPointF(p) for p in it.points])


def translated(it: Item, dx: float, dy: float) -> Item:
    out = clone(it)
    out.p1 = QPointF(it.p1.x() + dx, it.p1.y() + dy)
    out.p2 = QPointF(it.p2.x() + dx, it.p2.y() + dy)
    out.points = [QPointF(p.x() + dx, p.y() + dy) for p in it.points]
    return out


def number_radius(it: Item) -> float:
    return it.width * 1.6 + 8.0 * it.unit


def item_bounds(it: Item) -> QRectF:
    """Umgebendes Rechteck (Bildpixel) für Auswahlrahmen und Treffer."""
    k = it.kind
    if k in ("pen", "marker"):
        if not it.points:
            return QRectF()
        xs = [p.x() for p in it.points]
        ys = [p.y() for p in it.points]
        pad = (it.width * (3.2 if k == "marker" else 1.0)) / 2
        return QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad,
                      max(ys) - min(ys) + 2 * pad)
    if k == "text":
        font = QFont()
        font.setPixelSize(int(text_px(it)))
        r = QFontMetricsF(font).boundingRect(QRectF(0, 0, 6000, 6000),
                                             Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignTop.value
                                             | Qt.TextFlag.TextDontClip.value, it.text)
        return QRectF(it.p1.x(), it.p1.y(), max(r.width(), 8.0), max(r.height(), 8.0))
    if k == "number":
        r = number_radius(it)
        return QRectF(it.p1.x() - r, it.p1.y() - r, 2 * r, 2 * r)
    pad = it.width / 2 if k in ("rect", "ellipse", "line", "arrow") else 0.0
    return it.rect().adjusted(-pad, -pad, pad, pad)


def _dist_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length2))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


def hit_test(it: Item, pt: QPointF, tol: float) -> bool:
    """Liegt pt auf dem Element? tol = Toleranz in Bildpixeln (Mausungenauigkeit)."""
    k = it.kind
    if k in ("pen", "marker"):
        reach = tol + it.width * (3.2 if k == "marker" else 1.0) / 2
        if len(it.points) == 1:
            return math.hypot(pt.x() - it.points[0].x(), pt.y() - it.points[0].y()) <= reach
        return any(_dist_segment(pt, a, b) <= reach for a, b in zip(it.points, it.points[1:]))
    if k in LINE_ITEMS:
        reach = tol + max(it.width / 2, (it.width * 1.75 if k == "arrow" else 0.0))
        return _dist_segment(pt, it.p1, it.p2) <= reach
    if k == "rect":
        r = it.rect()
        outer = r.adjusted(-tol - it.width / 2, -tol - it.width / 2, tol + it.width / 2, tol + it.width / 2)
        if it.filled:
            return outer.contains(pt)
        inner = r.adjusted(tol + it.width / 2, tol + it.width / 2, -tol - it.width / 2, -tol - it.width / 2)
        return outer.contains(pt) and not (inner.width() > 0 and inner.height() > 0 and inner.contains(pt))
    if k == "ellipse":
        r = it.rect()
        a = r.width() / 2 + it.width / 2 + tol
        b = r.height() / 2 + it.width / 2 + tol
        if a <= 0 or b <= 0:
            return False
        c = r.center()
        outer = ((pt.x() - c.x()) / a) ** 2 + ((pt.y() - c.y()) / b) ** 2 <= 1.0
        if it.filled:
            return outer
        ai, bi = a - 2 * tol - it.width, b - 2 * tol - it.width
        inside = ai > 0 and bi > 0 and ((pt.x() - c.x()) / ai) ** 2 + ((pt.y() - c.y()) / bi) ** 2 < 1.0
        return outer and not inside
    if k in EFFECT_KINDS:
        return it.rect().adjusted(-tol, -tol, tol, tol).contains(pt)
    return item_bounds(it).adjusted(-tol, -tol, tol, tol).contains(pt)
