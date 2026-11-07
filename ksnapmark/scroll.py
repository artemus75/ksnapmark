"""Scrolling capture: the user scrolls the content, KSnapMark stitches the frames together."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

from .i18n import tr
from .stitch import ScrollSession

INTERVAL_MS = 350
HIDE_WAIT_MS = 150
PANEL_W, PANEL_H = 460, 64
BORDER = 3


class ScrollOverlay(QWidget):
    """Transparent full-screen window: frame around the region plus a small control panel.

    Only the frame and the panel receive input (window mask), so scrolling over the region reaches the
    application below. Frame and panel lie outside the captured region and are not part of the result.
    If the panel has to overlap the region (almost full-screen region), it is hidden while grabbing.
    """

    finished = Signal(QImage)
    cancelled = Signal()

    def __init__(self, screen, region_px: QRect, ratio: float, grab, interval_ms: int = INTERVAL_MS):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self._screen = screen
        self._grab = grab              # () -> QImage | None (the region, real pixels)
        self._interval = interval_ms
        self.session = ScrollSession()
        self.status = tr("Scroll the content slowly …")
        self._panel_visible = True
        self._done = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        geo = screen.geometry()
        self.setGeometry(geo)
        r = max(ratio, 0.01)
        self.region = QRect(round(region_px.x() / r), round(region_px.y() / r),
                            round(region_px.width() / r), round(region_px.height() / r))
        self.panel = self._place_panel(geo.width(), geo.height())
        self.overlap = self.panel.intersects(self.region)
        self._finish_btn = QRect(self.panel.right() - 190, self.panel.bottom() - 34, 100, 26)
        self._cancel_btn = QRect(self.panel.right() - 84, self.panel.bottom() - 34, 76, 26)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._update_mask()

    # --- layout -------------------------------------------------------------
    def _place_panel(self, w: int, h: int) -> QRect:
        x = max(0, min(w - PANEL_W, self.region.center().x() - PANEL_W // 2))
        candidates = [
            QRect(x, self.region.top() - PANEL_H - BORDER - 6, PANEL_W, PANEL_H),
            QRect(x, self.region.bottom() + BORDER + 6, PANEL_W, PANEL_H),
            QRect(self.region.right() + BORDER + 6, max(0, self.region.top()), PANEL_W, PANEL_H),
            QRect(self.region.left() - BORDER - 6 - PANEL_W, max(0, self.region.top()), PANEL_W, PANEL_H),
        ]
        screen = QRect(0, 0, w, h)
        for c in candidates:
            if screen.contains(c) and not c.intersects(self.region):
                return c
        return QRect((w - PANEL_W) // 2, 12, PANEL_W, PANEL_H)

    def _update_mask(self) -> None:
        outer = self.region.adjusted(-BORDER, -BORDER, BORDER, BORDER)
        ring = QRegion(outer).subtracted(QRegion(self.region))
        if self._panel_visible:
            ring = ring.united(QRegion(self.panel))
        self.setMask(ring)

    # --- run -------------------------------------------------------------------
    def start(self) -> None:
        self.showFullScreen()
        self._timer.start(300)

    def _tick(self) -> None:
        if self._done:
            return
        if self.overlap:
            self._panel_visible = False
            self._update_mask()
            self.repaint()
            QTimer.singleShot(HIDE_WAIT_MS, self._take)
        else:
            self._take()

    def _take(self) -> None:
        if self._done:
            return
        try:
            frame = self._grab()
        except Exception:  # noqa: BLE001 - a failed grab must not end the session
            frame = None
        if self.overlap:
            self._panel_visible = True
            self._update_mask()
        if frame is not None and not frame.isNull():
            state = self.session.add(frame)
            if state == "lost" and self.session.lost >= 3:
                self.status = tr("Lost track – scroll back a little, more slowly")
            elif state in ("added", "first"):
                self.status = tr("{n} frames · {h} px high").format(n=self.session.frames, h=self.session.height)
        self.update()
        if self.session.full:
            self.finish()
        elif not self._done:
            self._timer.start(self._interval)

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        img = self.session.result()
        self.close()
        if img is None:
            self.cancelled.emit()
        else:
            self.finished.emit(img)

    def cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.close()
        self.cancelled.emit()

    # --- painting and input ---------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        outer = self.region.adjusted(-BORDER, -BORDER, BORDER, BORDER)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#4ea1ff"))
        p.drawRect(outer)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawRect(self.region)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self._panel_visible:
            p.fillRect(self.panel, QColor(20, 20, 24, 240))
            font = QFont()
            font.setPixelSize(14)
            p.setFont(font)
            p.setPen(QColor("#ffffff"))
            p.drawText(self.panel.adjusted(12, 6, -12, -38), Qt.AlignmentFlag.AlignVCenter.value, self.status)
            for rect, text, color in ((self._finish_btn, tr("Finish"), "#2f81f7"),
                                      (self._cancel_btn, tr("Cancel"), "#555a66")):
                p.fillRect(rect, QColor(color))
                p.setPen(QPen(QColor("#ffffff")))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter.value, text)
        p.end()

    def mousePressEvent(self, e) -> None:
        pos: QPoint = e.position().toPoint()
        if e.button() == Qt.MouseButton.LeftButton:
            if self._finish_btn.contains(pos):
                self.finish()
            elif self._cancel_btn.contains(pos):
                self.cancel()
        elif e.button() == Qt.MouseButton.RightButton and self.panel.contains(pos):
            self.cancel()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.cancel()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.finish()
        else:
            super().keyPressEvent(e)
