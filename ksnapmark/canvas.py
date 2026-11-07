"""Zeichenfläche mit Undo/Redo, Zuschnitt und Zoom."""

from __future__ import annotations

from .i18n import tr

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QInputDialog, QWidget

from .items import (BOX_ITEMS, LINE_ITEMS, Item, clone, draw_preview, hit_test, item_bounds, render,
                    translated)

PEN_KINDS = ("pen", "marker")
LINEAR_KINDS = ("line", "arrow")
BOX_KINDS = ("rect", "ellipse", "blur", "pixel", "redact", "spot", "crop")


HANDLE_PX = 9.0   # Größe der Anfasser und Fangradius (Bildschirmpixel)
CLICK_TOL_PX = 6.0
DRAG_START_PX = 3.0


class _Drag:
    """Laufendes Verschieben/Anpassen eines ausgewählten Elements."""

    def __init__(self, mode: str, handle: str, start: QPointF, orig: Item):
        self.mode, self.handle, self.start, self.orig = mode, handle, start, orig
        self.started = False


class Canvas(QWidget):
    changed = Signal()
    selection_changed = Signal(object)  # ausgewähltes Item oder None
    message = Signal(str)
    picked = Signal(str)  # Farbe der Pipette als #rrggbb

    def __init__(self, image: QImage, dpr: float = 1.0, parent=None):
        super().__init__(parent)
        self.base = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self.base.setDevicePixelRatio(1.0)
        self.dpr = max(0.5, float(dpr))
        self.items: list[Item] = []
        self._undo: list[tuple[QImage, list[Item]]] = []
        self._redo: list[tuple[QImage, list[Item]]] = []
        self.tool = "arrow"
        self.color = "#ff2d2d"
        self.width = 6
        self.filled = False
        self.zoom = 1.0
        self._cache: QImage | None = None
        self._current: Item | None = None
        self.selected: Item | None = None
        self._drag: _Drag | None = None
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._relayout()

    def set_tool(self, name: str) -> None:
        self.tool = name
        if name != "select":
            self._set_selected(None)
        self.setCursor(Qt.CursorShape.ArrowCursor if name == "select" else Qt.CursorShape.CrossCursor)

    # --- Geometrie -----------------------------------------------------
    @property
    def view_scale(self) -> float:
        return self.zoom / self.dpr

    def logical_size(self) -> tuple[float, float]:
        return self.base.width() / self.dpr, self.base.height() / self.dpr

    def _relayout(self) -> None:
        s = self.view_scale
        self.setFixedSize(max(1, round(self.base.width() * s)), max(1, round(self.base.height() * s)))
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = min(8.0, max(0.1, zoom))
        self._relayout()
        self.message.emit(f"Zoom {round(self.zoom * 100)} %")

    def _to_img(self, pos: QPointF) -> QPointF:
        s = self.view_scale
        x = min(max(pos.x() / s, 0.0), float(self.base.width()))
        y = min(max(pos.y() / s, 0.0), float(self.base.height()))
        return QPointF(x, y)

    # --- Zustand / Undo --------------------------------------------------
    def _push_undo(self) -> None:
        self._undo.append((self.base, list(self.items)))
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append((self.base, list(self.items)))
        self.base, self.items = self._undo.pop()
        self._set_selected(None, emit_only_if_changed=True)
        self._state_changed(relayout=True)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append((self.base, list(self.items)))
        self.base, self.items = self._redo.pop()
        self._set_selected(None, emit_only_if_changed=True)
        self._state_changed(relayout=True)

    def _state_changed(self, relayout: bool = False) -> None:
        self._cache = None
        if relayout:
            self._relayout()
        self.update()
        self.changed.emit()

    def result_image(self) -> QImage:
        return render(self.base, self.items)

    def add_effects(self, rects: list[QRectF], kind: str = "redact", adaptive: bool = False) -> None:
        """Effekte auf Rechtecke legen. adaptive: Stärke an die Texthöhe anpassen, sodass
        Schrift sicher unlesbar wird (Blockgröße ≈ halbe Zeilenhöhe)."""
        if not rects:
            return
        self._push_undo()
        for r in rects:
            width = self.width * self.dpr
            if adaptive and kind != "redact":
                width = max(width, r.height() / 4.0)
            self.items.append(Item(kind=kind, width=width,
                                   p1=r.topLeft(), p2=r.bottomRight(), unit=self.dpr))
        self._state_changed()

    def apply_crop(self, rect: QRectF) -> None:
        r = rect.normalized().toAlignedRect().intersected(self.base.rect())
        if r.width() < 4 or r.height() < 4:
            return
        flat = self.result_image()
        self._push_undo()
        self.base = flat.copy(r)
        self.items = []
        self._set_selected(None, emit_only_if_changed=True)
        self._state_changed(relayout=True)
        self.message.emit(tr("Cropped to {w} × {h}").format(w=r.width(), h=r.height()))

    def apply_frame(self, **options) -> None:
        """Put the flattened image on a background with rounded corners and shadow (undoable)."""
        from .frame import add_frame

        flat = self.result_image()
        framed = add_frame(flat, **options)
        self._push_undo()
        self.base = framed
        self.items = []
        self._set_selected(None, emit_only_if_changed=True)
        self._state_changed(relayout=True)
        self.message.emit(tr("Frame added ({w} × {h})").format(w=framed.width(), h=framed.height()))

    # --- Zeichnen --------------------------------------------------------
    def _get_cache(self) -> QImage:
        if self._cache is None:
            self._cache = render(self.base, self.items)
        return self._cache

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        s = self.view_scale
        p.scale(s, s)
        p.drawImage(0, 0, self._get_cache())
        if self._current is not None:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            draw_preview(p, self._current,
                         QRectF(0, 0, self.base.width(), self.base.height()))
        if self.selected is not None:
            self._paint_selection(p)
        p.end()

    def _paint_selection(self, p: QPainter) -> None:
        it = self.selected
        rect = item_bounds(it)
        if rect.isNull():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for color, style in ((QColor(0, 0, 0, 200), Qt.PenStyle.SolidLine),
                             (QColor(255, 255, 255, 230), Qt.PenStyle.DashLine)):
            pen = QPen(color, 0, style)  # Breite 0 = immer 1 Bildschirmpixel
            p.setPen(pen)
            p.drawRect(rect)
        half = HANDLE_PX / 2 / self.view_scale
        p.setPen(QPen(QColor(0, 0, 0, 230), 0))
        p.setBrush(QColor(255, 255, 255))
        for pt in self._handles(it).values():
            p.drawRect(QRectF(pt.x() - half, pt.y() - half, 2 * half, 2 * half))

    # --- Auswahl ------------------------------------------------------------
    def _set_selected(self, it: Item | None, emit_only_if_changed: bool = False) -> None:
        if emit_only_if_changed and it is None and self.selected is None:
            return
        changed = it is not self.selected
        self.selected = it
        self.update()
        if changed or not emit_only_if_changed:
            self.selection_changed.emit(it)

    def deselect(self) -> None:
        self._set_selected(None, emit_only_if_changed=True)

    def _index_of(self, it: Item | None) -> int:
        for i, cand in enumerate(self.items):
            if cand is it:
                return i
        return -1

    def _handles(self, it: Item) -> dict[str, QPointF]:
        if it.kind in BOX_ITEMS:
            r = it.rect()
            return {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
        if it.kind in LINE_ITEMS:
            return {"p1": it.p1, "p2": it.p2}
        return {}

    def _handle_at(self, pos: QPointF) -> str | None:
        if self.selected is None:
            return None
        reach = HANDLE_PX / self.view_scale
        for name, pt in self._handles(self.selected).items():
            if math.hypot(pos.x() - pt.x(), pos.y() - pt.y()) <= reach:
                return name
        return None

    def item_at(self, pos: QPointF) -> Item | None:
        tol = CLICK_TOL_PX / self.view_scale
        for it in reversed(self.items):
            if hit_test(it, pos, tol):
                return it
        return None

    def _select_press(self, pos: QPointF) -> None:
        handle = self._handle_at(pos)
        if handle is not None:
            self._drag = _Drag("handle", handle, pos, self.selected)
            return
        it = self.item_at(pos)
        self._set_selected(it, emit_only_if_changed=True)
        if it is not None:
            self._drag = _Drag("move", "", pos, it)

    def _drag_to(self, pos: QPointF, shift: bool) -> None:
        d = self._drag
        if not d.started:
            if math.hypot(pos.x() - d.start.x(), pos.y() - d.start.y()) * self.view_scale < DRAG_START_PX:
                return
            d.started = True
            self._push_undo()  # der Schnappschuss enthält das unveränderte Original
        idx = self._index_of(self.selected)
        if idx < 0:
            return
        if d.mode == "move":
            new = translated(d.orig, pos.x() - d.start.x(), pos.y() - d.start.y())
        else:
            new = self._resized(d.orig, d.handle, pos, shift)
        self.items[idx] = new
        self.selected = new
        self._cache = None
        self.update()

    def _resized(self, orig: Item, handle: str, pos: QPointF, shift: bool) -> Item:
        new = clone(orig)
        if orig.kind in LINE_ITEMS:
            fixed = orig.p2 if handle == "p1" else orig.p1
            moving = QPointF(pos)
            if shift:
                probe = Item(kind="line", p1=fixed)
                moving = self._constrain(probe, pos, True)
            if handle == "p1":
                new.p1, new.p2 = moving, QPointF(orig.p2)
            else:
                new.p1, new.p2 = QPointF(orig.p1), moving
            return new
        r = orig.rect()
        fixed = {"tl": r.bottomRight(), "tr": r.bottomLeft(), "bl": r.topRight(), "br": r.topLeft()}[handle]
        moving = QPointF(pos)
        if shift:
            probe = Item(kind="rect", p1=fixed)
            moving = self._constrain(probe, pos, True)
        box = QRectF(fixed, moving).normalized()
        new.p1, new.p2 = box.topLeft(), box.bottomRight()
        return new

    def delete_selected(self) -> bool:
        it = self.selected
        idx = self._index_of(it)
        if it is None or idx < 0:
            return False
        self._push_undo()
        del self.items[idx]
        if it.kind == "number":  # Nummern lückenlos halten
            n = 0
            for i, cand in enumerate(self.items):
                if cand.kind == "number":
                    n += 1
                    if cand.number != n:
                        new = clone(cand)
                        new.number = n
                        self.items[i] = new
        self._set_selected(None, emit_only_if_changed=True)
        self._state_changed()
        return True

    def nudge(self, dx: float, dy: float) -> bool:
        it = self.selected
        idx = self._index_of(it)
        if it is None or idx < 0:
            return False
        self._push_undo()
        new = translated(it, dx, dy)
        self.items[idx] = new
        self.selected = new
        self._state_changed()
        return True

    def apply_to_selected(self, color: str | None = None, width: float | None = None,
                          filled: bool | None = None) -> bool:
        """Farbe/Stärke/Füllung des ausgewählten Elements ändern (ein Undo-Schritt)."""
        it = self.selected
        idx = self._index_of(it)
        if it is None or idx < 0:
            return False
        new = clone(it)
        if color is not None:
            new.color = color
        if width is not None:
            new.width = width * self.dpr
        if filled is not None and it.kind in ("rect", "ellipse"):
            new.filled = filled
        if (new.color, new.width, new.filled) == (it.color, it.width, it.filled):
            return False
        self._push_undo()
        self.items[idx] = new
        self.selected = new
        self._state_changed()
        return True

    def _update_hover_cursor(self, pos: QPointF) -> None:
        handle = self._handle_at(pos)
        if handle is not None:
            diag = handle in ("tl", "br")
            if handle in ("p1", "p2"):
                shape = Qt.CursorShape.CrossCursor
            else:
                shape = Qt.CursorShape.SizeFDiagCursor if diag else Qt.CursorShape.SizeBDiagCursor
        elif self.item_at(pos) is not None:
            shape = Qt.CursorShape.SizeAllCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.setCursor(shape)

    def keyPressEvent(self, e) -> None:
        if self.selected is not None:
            key = e.key()
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected()
                return
            step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                     Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
            if key in moves:
                self.nudge(*moves[key])
                return
        super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if self.tool == "select" and e.button() == Qt.MouseButton.LeftButton:
            it = self.item_at(self._to_img(e.position()))
            if it is not None and it.kind == "text":
                self._set_selected(it, emit_only_if_changed=True)
                self.edit_text(it)
                return
        super().mouseDoubleClickEvent(e)

    def edit_text(self, it: Item) -> None:
        idx = self._index_of(it)
        if idx < 0:
            return
        text, ok = QInputDialog.getMultiLineText(self.window(), "Text", tr("Enter text:"), it.text)
        text = text.strip("\n")
        if not ok or not text.strip() or text == it.text:
            return
        self._push_undo()
        new = clone(it)
        new.text = text
        self.items[idx] = new
        self.selected = new
        self._state_changed()

    # --- Eingaben --------------------------------------------------------
    def _new_item(self, pos: QPointF) -> Item:
        kind = self.tool
        return Item(kind=kind, color=self.color, width=self.width * self.dpr, p1=pos, p2=pos,
                    points=[pos] if kind in PEN_KINDS else [], filled=self.filled, unit=self.dpr)

    def _constrain(self, it: Item, pos: QPointF, shift: bool) -> QPointF:
        if not shift:
            return pos
        a = it.p1
        dx, dy = pos.x() - a.x(), pos.y() - a.y()
        if it.kind in LINEAR_KINDS:
            step = math.pi / 4
            ang = round(math.atan2(dy, dx) / step) * step
            d = math.hypot(dx, dy)
            return QPointF(a.x() + d * math.cos(ang), a.y() + d * math.sin(ang))
        if it.kind in BOX_KINDS:
            s = max(abs(dx), abs(dy))
            return QPointF(a.x() + math.copysign(s, dx), a.y() + math.copysign(s, dy))
        return pos

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._to_img(e.position())
        self.setFocus()
        if self.tool == "select":
            self._select_press(pos)
            return
        if self.tool == "pick":
            img = self._get_cache()
            x, y = int(pos.x()), int(pos.y())
            if 0 <= x < img.width() and 0 <= y < img.height():
                self.picked.emit(img.pixelColor(x, y).name())
            return
        if self.tool == "text":
            self._place_text(pos)
            return
        if self.tool == "number":
            self._place_number(pos)
            return
        self._current = self._new_item(pos)
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            self._drag_to(self._to_img(e.position()), bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return
        it = self._current
        if it is None:
            if self.tool == "select":
                self._update_hover_cursor(self._to_img(e.position()))
            return
        pos = self._to_img(e.position())
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if it.kind in PEN_KINDS:
            last = it.points[-1]
            if math.hypot(pos.x() - last.x(), pos.y() - last.y()) >= 1.5:
                it.points.append(pos)
        else:
            it.p2 = self._constrain(it, pos, shift)
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag is not None and e.button() == Qt.MouseButton.LeftButton:
            moved = self._drag.started
            self._drag = None
            if moved:
                self._state_changed()
            return
        it = self._current
        if it is None or e.button() != Qt.MouseButton.LeftButton:
            return
        self._current = None
        if it.kind not in PEN_KINDS:
            shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            it.p2 = self._constrain(it, self._to_img(e.position()), shift)
            if math.hypot(it.p2.x() - it.p1.x(), it.p2.y() - it.p1.y()) < 3 * self.dpr:
                self.update()
                return
        if it.kind == "crop":
            self.apply_crop(it.rect())
            return
        self._push_undo()
        self.items.append(it)
        self._state_changed()

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom * (1.1 ** (e.angleDelta().y() / 120)))
            e.accept()
        else:
            e.ignore()

    # --- Text und Nummern ---------------------------------------------------
    def _place_text(self, pos: QPointF) -> None:
        text, ok = QInputDialog.getMultiLineText(self.window(), "Text", tr("Enter text:"))
        text = text.strip("\n")
        if not ok or not text.strip():
            return
        it = Item(kind="text", color=self.color, width=self.width * self.dpr, p1=pos, p2=pos,
                  text=text, unit=self.dpr)
        self._push_undo()
        self.items.append(it)
        self._state_changed()

    def _place_number(self, pos: QPointF) -> None:
        n = 1 + sum(1 for i in self.items if i.kind == "number")
        it = Item(kind="number", color=self.color, width=self.width * self.dpr, p1=pos, p2=pos,
                  number=n, unit=self.dpr)
        self._push_undo()
        self.items.append(it)
        self._state_changed()
