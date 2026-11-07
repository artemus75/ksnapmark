"""Vollbild-Overlay: eingefrorener Bildschirm, Bereich mit der Maus aufziehen."""

from __future__ import annotations

from .i18n import tr

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import config, system

LOUPE_PIXELS = 15   # Bildpunkte, die die Lupe zeigt (ungerade)
LOUPE_ZOOM = 9


class SelectionOverlay(QWidget):
    selected = Signal(QImage, float)  # Ausschnitt in echten Pixeln, Skalierung des Monitors
    cancelled = Signal()

    def __init__(self, screen, shot: QImage, windows: list | None = None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._screen = screen
        self._shot = shot
        self._anchor: QPoint | None = None
        self._cur = QPoint()
        self._bg: QPixmap | None = None
        self._dim: QPixmap | None = None
        self._bg_size = None
        # Fenster dieses Monitors (oberstes zuerst), Koordinaten relativ zum Overlay
        self._wins: list[tuple[QRect, str]] = self._local_windows(windows or [])
        self._hover: QRect | None = None
        self._hover_title = ""
        self._press_pos: QPoint | None = None
        self.region: QRect | None = None   # last chosen region in real pixels
        try:
            self.show_loupe = config.load().show_loupe
        except Exception:
            self.show_loupe = False
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setWindowTitle("KSnapMark")

    def _local_windows(self, windows: list) -> list[tuple[QRect, str]]:
        geo = self._screen.geometry()
        out = []
        for w in reversed(windows):  # Stapel: unten -> oben; für die Suche oberstes zuerst
            local = w.rect.translated(-geo.x(), -geo.y()).intersected(QRect(0, 0, geo.width(), geo.height()))
            if local.width() >= 20 and local.height() >= 20:
                out.append((local, w.title))
        return out

    def window_at(self, pos: QPoint) -> tuple[QRect, str] | None:
        for rect, title in self._wins:
            if rect.contains(pos):
                return rect, title
        return None

    # --- Anzeige -------------------------------------------------------
    def show_on_screen(self) -> None:
        self.setGeometry(self._screen.geometry())
        self.show()
        handle = self.windowHandle()
        if handle is not None:
            try:
                handle.setScreen(self._screen)
            except Exception:
                pass
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def _ratio(self) -> float:
        return self._shot.width() / max(1, self.width())

    def _ensure_pixmaps(self) -> None:
        size = (self.width(), self.height())
        if self._bg is not None and self._bg_size == size:
            return
        pm = QPixmap.fromImage(self._shot)
        pm.setDevicePixelRatio(self._ratio())
        dim = QPixmap(pm)
        dim.setDevicePixelRatio(self._ratio())
        painter = QPainter(dim)
        painter.fillRect(QRectF(0, 0, self.width(), self.height()), QColor(0, 0, 0, 125))
        painter.end()
        self._bg, self._dim, self._bg_size = pm, dim, size

    def _selection(self) -> QRect | None:
        if self._anchor is None:
            return None
        return QRect(self._anchor, self._cur).normalized()

    # --- Zeichnen ------------------------------------------------------
    def paintEvent(self, _event) -> None:
        self._ensure_pixmaps()
        assert self._bg is not None and self._dim is not None
        p = QPainter(self)
        p.drawPixmap(0, 0, self._dim)
        sel = self._selection()
        if sel is not None and sel.width() > 0 and sel.height() > 0:
            p.save()
            p.setClipRect(sel)
            p.drawPixmap(0, 0, self._bg)
            p.restore()
            p.setPen(QPen(QColor("#4ea1ff"), 1.5))
            p.drawRect(sel.adjusted(0, 0, -1, -1))
            ratio = self._ratio()
            self._label(p, sel, f"{round(sel.width() * ratio)} × {round(sel.height() * ratio)}")
        else:
            if self._hover is not None:
                p.save()
                p.setClipRect(self._hover)
                p.drawPixmap(0, 0, self._bg)
                p.restore()
                p.setPen(QPen(QColor("#4ea1ff"), 2))
                p.drawRect(self._hover.adjusted(1, 1, -1, -1))
                ratio = self._ratio()
                label = f"{self._hover_title[:48]}  ·  {round(self._hover.width() * ratio)} × {round(self._hover.height() * ratio)}"
                self._label(p, self._hover, label.strip(" ·"))
            else:
                self._crosshair(p)
            self._hint(p)
        if self.show_loupe:
            self._loupe(p)
        p.end()

    def _shot_pos(self) -> tuple[int, int]:
        """Mauszeiger in echten Bildpunkten des Screenshots."""
        r = self._ratio()
        return (min(max(0, int(self._cur.x() * r)), self._shot.width() - 1),
                min(max(0, int(self._cur.y() * r)), self._shot.height() - 1))

    def color_under_cursor(self) -> QColor:
        x, y = self._shot_pos()
        return self._shot.pixelColor(x, y)

    def _loupe(self, p: QPainter) -> None:
        """Lupe neben dem Mauszeiger: vergrößerter Ausschnitt, Farbwert, Position."""
        x, y = self._shot_pos()
        half = LOUPE_PIXELS // 2
        src = QRect(x - half, y - half, LOUPE_PIXELS, LOUPE_PIXELS)
        patch = QImage(LOUPE_PIXELS, LOUPE_PIXELS, QImage.Format.Format_RGB32)
        patch.fill(QColor(20, 20, 24))  # außerhalb des Bildes dunkel lassen
        inter = src.intersected(self._shot.rect())
        painter = QPainter(patch)
        painter.drawImage(QPoint(inter.x() - src.x(), inter.y() - src.y()), self._shot, inter)
        painter.end()
        size = LOUPE_PIXELS * LOUPE_ZOOM
        big = patch.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        col = self._shot.pixelColor(x, y)
        info_h = 38
        w, h = max(size + 8, 262), size + 8 + info_h
        ox, oy = self._cur.x() + 22, self._cur.y() + 22
        if ox + w > self.width():
            ox = self._cur.x() - 22 - w
        if oy + h > self.height():
            oy = self._cur.y() - 22 - h
        ox, oy = max(0, ox), max(0, oy)
        p.save()
        p.fillRect(QRect(ox, oy, w, h), QColor(20, 20, 24, 235))
        img_x = ox + (w - size) // 2
        p.drawImage(QPoint(img_x, oy + 4), big)
        c = LOUPE_PIXELS // 2 * LOUPE_ZOOM
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawRect(QRect(img_x + c, oy + 4 + c, LOUPE_ZOOM, LOUPE_ZOOM))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.drawRect(QRect(img_x + c - 1, oy + 3 + c, LOUPE_ZOOM + 2, LOUPE_ZOOM + 2))
        font = QFont()
        font.setPixelSize(12)
        p.setFont(font)
        p.fillRect(QRect(ox + 6, oy + size + 14, 22, 22), col)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        p.drawRect(QRect(ox + 6, oy + size + 14, 22, 22))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(ox + 34, oy + size + 10, w - 38, 16), Qt.AlignmentFlag.AlignVCenter.value,
                   f"{col.name().upper()}   rgb({col.red()}, {col.green()}, {col.blue()})")
        p.setPen(QColor(200, 200, 210))
        p.drawText(QRect(ox + 34, oy + size + 26, w - 38, 16), Qt.AlignmentFlag.AlignVCenter.value,
                   tr("x {x}  y {y}   ·   C: copy color").format(x=x, y=y))
        p.restore()

    def _crosshair(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        p.drawLine(self._cur.x(), 0, self._cur.x(), self.height())
        p.drawLine(0, self._cur.y(), self.width(), self._cur.y())

    def _label(self, p: QPainter, sel: QRect, text: str) -> None:
        font = QFont()
        font.setPixelSize(13)
        p.setFont(font)
        w = p.fontMetrics().horizontalAdvance(text) + 14
        h = 22
        x = sel.left()
        y = sel.top() - h - 4 if sel.top() > h + 6 else sel.top() + 4
        p.fillRect(QRect(x, y, w, h), QColor(20, 20, 24, 220))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter.value, text)

    def _hint(self, p: QPainter) -> None:
        text = (tr("Drag a region") + (tr("  or  click a window") if self._wins else "") +
                tr("   ·   Space: full screen   ·   L: magnifier   ·   Esc: cancel"))
        font = QFont()
        font.setPixelSize(14)
        p.setFont(font)
        w = p.fontMetrics().horizontalAdvance(text) + 28
        rect = QRect((self.width() - w) // 2, 28, w, 32)
        p.fillRect(rect, QColor(20, 20, 24, 225))
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter.value, text)

    # --- Eingaben ------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._anchor = e.position().toPoint()
            self._press_pos = self._anchor
            self._cur = self._anchor
            self.update()

    def mouseMoveEvent(self, e) -> None:
        self._cur = e.position().toPoint()
        if self._anchor is None and self._wins:  # Fenster unter dem Zeiger hervorheben
            hit = self.window_at(self._cur)
            self._hover, self._hover_title = (hit if hit else (None, ""))
        elif self._anchor is not None:
            self._hover = None
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._anchor is None:
            return
        self._cur = e.position().toPoint()
        sel = self._selection()
        self._anchor = None
        if sel is None or sel.width() < 4 or sel.height() < 4:
            # Klick ohne Ziehen: das Fenster unter dem Zeiger auswählen
            hit = self.window_at(self._cur) if self._wins else None
            self._press_pos = None
            if hit is not None:
                self._emit_region(hit[0])
                return
            self.update()
            return
        self._press_pos = None
        self._emit_region(sel)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif e.key() == Qt.Key.Key_L and not e.modifiers():
            self.show_loupe = not self.show_loupe
            self.update()
        elif e.key() == Qt.Key.Key_C and not e.modifiers():
            self.copy_color()
        elif e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F):
            self._emit_region(QRect(0, 0, self.width(), self.height()))
        else:
            super().keyPressEvent(e)

    def copy_color(self) -> str:
        """Farbe unter dem Mauszeiger als Hex-Wert kopieren (Auswahl bleibt offen)."""
        hex_value = self.color_under_cursor().name().upper()
        if system.clipboard_set_text(hex_value):
            system.notify("KSnapMark", tr("Color {color} copied").format(color=hex_value))
        else:
            QGuiApplication.clipboard().setText(hex_value)
            system.request_keepalive()
            system.notify("KSnapMark", tr("Color {color} copied").format(color=hex_value))
        return hex_value

    def _emit_region(self, sel: QRect) -> None:
        ratio = self._ratio()
        rect = QRect(round(sel.x() * ratio), round(sel.y() * ratio),
                     round(sel.width() * ratio), round(sel.height() * ratio))
        rect = rect.intersected(self._shot.rect())
        if rect.width() < 2 or rect.height() < 2:
            return
        img = self._shot.copy(rect)
        img.setDevicePixelRatio(1.0)
        self.region = rect
        self.selected.emit(img, ratio)


def screens_to_cover(name: str | None = None) -> list:
    """Alle Monitore – oder nur der per --screen angegebene."""
    screens = list(QGuiApplication.screens())
    if name:
        chosen = [s for s in screens if s.name() == name]
        if chosen:
            return chosen
    return screens


def current_screen(name: str | None = None):
    """Monitor wählen: per Name, sonst der unter dem Mauszeiger, sonst der primäre."""
    from PySide6.QtGui import QCursor

    if name:
        for s in QGuiApplication.screens():
            if s.name() == name:
                return s
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
