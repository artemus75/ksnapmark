"""Angeheftetes Bild: rahmenloses, schwebendes Fenster mit einem Screenshot als Referenz.

Bedienung: ziehen = verschieben · Mausrad = Größe · Strg+Mausrad = Transparenz ·
Doppelklick / Esc = schließen · Rechtsklick = Menü.

Hinweis Wayland: Ob das Fenster über allen anderen bleibt, entscheidet der Desktop. Unter KDE:
Alt+F3 (Fenstermenü) → „Weitere Aktionen“ → „Immer im Vordergrund halten“, oder eine Fensterregel.
"""

from __future__ import annotations

from .i18n import tr

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QImage, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from . import system

MIN_WIDTH = 60
OPACITY_STEPS = (1.0, 0.8, 0.6, 0.4)


class PinWindow(QWidget):
    open_in_editor = Signal(QImage)

    def __init__(self, image: QImage, dpr: float = 1.0):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._image = QImage(image)
        self._image.setDevicePixelRatio(1.0)
        self._pixmap = QPixmap.fromImage(self._image)
        self._ratio = self._image.height() / max(1, self._image.width())
        self._opacity = 1.0
        self._drag_pos: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(tr("KSnapMark – pinned"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tr("Drag: move · Wheel: size · Ctrl+wheel: transparency · Double-click: close"))
        w = max(MIN_WIDTH, round(self._image.width() / max(0.5, dpr)))
        screen = QGuiApplication.primaryScreen()
        if screen is not None:  # nie größer als der Monitor beim Anheften
            avail = screen.availableGeometry()
            w = min(w, avail.width() - 40, round((avail.height() - 40) / self._ratio))
        self.resize(self._size_for_width(w))

    def _size_for_width(self, w: int) -> QSize:
        w = max(MIN_WIDTH, w)
        return QSize(w, max(1, round(w * self._ratio)))

    # --- Zeichnen ---------------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setOpacity(self._opacity)
        p.drawPixmap(self.rect(), self._pixmap)
        p.setPen(QPen(QColor(78, 161, 255, 200), 1))
        p.drawRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1))
        p.end()

    # --- Eingaben ---------------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return  # Wayland/X11: der Desktop übernimmt das Verschieben
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.close()

    def wheelEvent(self, e) -> None:
        delta = e.angleDelta().y()
        if not delta:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_opacity(self._opacity + (0.1 if delta > 0 else -0.1))
        else:
            factor = 1.1 if delta > 0 else 1 / 1.1
            self.resize(self._size_for_width(round(self.width() * factor)))

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        elif e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        menu.addAction(tr("Copy"), self.copy)
        menu.addAction(tr("Open in editor"), lambda: self.open_in_editor.emit(QImage(self._image)))
        menu.addAction(tr("Original size"), lambda: self.resize(self._size_for_width(self._image.width())))
        sub = menu.addMenu(tr("Transparency"))
        for value in OPACITY_STEPS:
            act = QAction(f"{round(value * 100)} %", sub)
            act.setCheckable(True)
            act.setChecked(abs(value - self._opacity) < 0.05)
            act.triggered.connect(lambda _=False, v=value: self.set_opacity(v))
            sub.addAction(act)
        menu.addSeparator()
        menu.addAction(tr("Close"), self.close)
        menu.exec(e.globalPos())

    # --- Aktionen -----------------------------------------------------------------------------
    def set_opacity(self, value: float) -> None:
        self._opacity = min(1.0, max(0.2, value))
        self.update()

    def copy(self) -> None:
        from .editor import png_bytes

        if not system.clipboard_set(png_bytes(self._image), "image/png"):
            QGuiApplication.clipboard().setImage(self._image)
            system.request_keepalive()
        system.notify("KSnapMark", tr("Pinned image copied"))
