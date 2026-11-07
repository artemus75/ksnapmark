"""History window: thumbnails of the latest captures with a text search (OCR index, local only)."""

from __future__ import annotations

import time

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from . import ocr
from .asyncutil import run_async
from .i18n import tr

THUMB = QSize(200, 125)


def entry_label(entry) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(entry.taken))


class HistoryDialog(QDialog):
    """Search field + thumbnails. Opens an entry in the editor (``open_entry``), deletes entries."""

    open_entry = Signal(str)

    def __init__(self, history, ocr_langs: str = "deu+eng", index_text: bool = True, parent=None):
        super().__init__(parent)
        self.history = history
        self._langs = ocr_langs
        self._closed = False
        self._indexing = False
        self.setWindowTitle(tr("History"))
        self.resize(900, 620)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search text in your screenshots …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)

        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(THUMB)
        self.list.setGridSize(QSize(THUMB.width() + 24, THUMB.height() + 44))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda _i: self.open_selected())

        self.status = QLabel("")
        self.status.setProperty("muted", True)
        self.open_btn = QPushButton(tr("Open in editor"))
        self.open_btn.clicked.connect(self.open_selected)
        self.delete_btn = QPushButton(tr("Delete"))
        self.delete_btn.clicked.connect(self.delete_selected)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)

        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(self.open_btn)
        row.addWidget(self.delete_btn)
        row.addWidget(close)
        root = QVBoxLayout(self)
        root.addWidget(self.search)
        root.addWidget(self.list, 1)
        root.addLayout(row)

        self.index_text = bool(index_text) and ocr.available()
        self.refresh()
        if self.index_text:
            self._index_next()
        elif index_text and not ocr.available():
            self.status.setText(tr("Text search needs Tesseract (sudo pacman -S tesseract)."))

    # --- list -------------------------------------------------------------------------------
    def refresh(self, *_args) -> None:
        query = self.search.text()
        entries = self.history.search(query)
        self.list.clear()
        for e in entries:
            pm = QPixmap(str(e.path))
            item = QListWidgetItem(entry_label(e))
            if not pm.isNull():
                item.setIcon(QIcon(pm.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)))
            item.setData(Qt.ItemDataRole.UserRole, e.name)
            snippet = (self.history.text_of(e.name) or "").strip().replace("\n", " ")
            if snippet:
                item.setToolTip(snippet[:300])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        if not self._indexing:
            total = len(self.history.entries())
            if query.strip():
                self.status.setText(tr("{n} of {total} screenshots match").format(n=len(entries), total=total))
            else:
                self.status.setText(tr("{total} screenshots").format(total=total))
        self.open_btn.setEnabled(self.list.count() > 0)
        self.delete_btn.setEnabled(self.list.count() > 0)

    def selected_name(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def open_selected(self) -> None:
        name = self.selected_name()
        if name:
            self.open_entry.emit(name)

    def delete_selected(self) -> None:
        name = self.selected_name()
        if name and self.history.delete(name):
            self.refresh()

    # --- background indexing ----------------------------------------------------------------
    def _index_next(self) -> None:
        if self._closed:
            self._indexing = False
            return
        todo = self.history.missing()
        if not todo:
            self._indexing = False
            self.refresh()
            return
        self._indexing = True
        entry = todo[0]
        self.status.setText(tr("Indexing text … ({n} left)").format(n=len(todo)))
        img = self.history.load(entry.name)
        if img is None:
            self.history.set_text(entry.name, "")
            self._index_next()
            return

        def done(text) -> None:
            self.history.set_text(entry.name, str(text or ""))
            if self.search.text().strip():
                self.refresh()
            self._index_next()

        def failed(_msg: str) -> None:
            self.history.set_text(entry.name, "")      # do not retry a broken image forever
            self._index_next()

        run_async(lambda: ocr.ocr_text(img, self._langs), done, failed)

    def closeEvent(self, event) -> None:
        self._closed = True
        super().closeEvent(event)
