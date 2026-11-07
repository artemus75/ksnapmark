"""Fenster der Ideen-Sammlung (Galerie, Suche, Tags, Notizen)."""

from __future__ import annotations

from .i18n import tr

from typing import Callable

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from . import icons, ideas, system
from .dialogs import IdeaDialog
from .ideas import Idea, IdeaStore


class ImageLabel(QLabel):
    """Zeigt ein Bild passend skaliert an und passt sich der Größe an."""

    def __init__(self) -> None:
        super().__init__()
        self._pm: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 160)
        self.setStyleSheet("background:#16171a; border-radius:8px;")

    def set_image(self, pm: QPixmap | None) -> None:
        self._pm = pm
        self._refresh()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self) -> None:
        if self._pm is None or self._pm.isNull():
            self.clear()
            return
        self.setPixmap(self._pm.scaled(self.size() - QSize(12, 12),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))


class IdeasWindow(QMainWindow):
    def __init__(self, store: IdeaStore, langs: str,
                 open_editor: Callable[[QImage, int], None]):
        super().__init__()
        self.store = store
        self.langs = langs
        self.open_editor = open_editor
        self._current: Idea | None = None
        self.setWindowTitle(tr("KSnapMark – Ideas Collection"))
        self.setWindowIcon(icons.app_icon())
        self.resize(1280, 780)

        # Kopfzeile
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search: title, note, tags, source or text in the image …"))
        self.search.setClearButtonEnabled(True)
        self.tag_box = QComboBox()
        self.tag_box.setMinimumWidth(170)
        paste_btn = QPushButton(tr("From clipboard"))
        paste_btn.setToolTip(tr("Add the image from the clipboard as an idea (Ctrl+V)"))
        paste_btn.clicked.connect(self.paste_from_clipboard)
        folder_btn = QPushButton(tr("Open folder"))
        folder_btn.clicked.connect(lambda: system.open_path(str(self.store.base)))
        head = QHBoxLayout()
        head.addWidget(self.search, 1)
        head.addWidget(self.tag_box)
        head.addWidget(paste_btn)
        head.addWidget(folder_btn)

        # Liste
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(260, 170))
        self.list.setGridSize(QSize(292, 232))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setSpacing(4)
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _i: self.edit_image())

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(10, 10, 6, 10)
        left_l.addLayout(head)
        left_l.addWidget(self.list, 1)

        # Detailbereich
        self.preview = ImageLabel()
        self.title = QLineEdit()
        self.tags = QLineEdit()
        self.source = QLineEdit()
        open_src = QPushButton(tr("Open"))
        open_src.clicked.connect(self._open_source)
        src_row = QHBoxLayout()
        src_row.addWidget(self.source, 1)
        src_row.addWidget(open_src)
        self.note = QPlainTextEdit()
        self.note.setFixedHeight(100)
        self.ocr_view = QPlainTextEdit()
        self.ocr_view.setReadOnly(True)
        self.ocr_view.setPlaceholderText(tr("Text from the image appears here once recognition has finished."))
        self.meta = QLabel("")
        self.meta.setProperty("muted", True)

        form = QFormLayout()
        form.addRow(tr("Title"), self.title)
        form.addRow("Tags", self.tags)
        form.addRow(tr("Source"), src_row)
        form.addRow(tr("Note"), self.note)

        self.btn_save = QPushButton(tr("Save"))
        self.btn_edit = QPushButton(tr("Edit image"))
        self.btn_copy = QPushButton(tr("Copy image"))
        self.btn_delete = QPushButton(tr("Delete"))
        self.btn_save.clicked.connect(self.save_current)
        self.btn_edit.clicked.connect(self.edit_image)
        self.btn_copy.clicked.connect(self.copy_image)
        self.btn_delete.clicked.connect(self.delete_current)
        self.btn_save.setIcon(icons.icon("save"))
        self.btn_edit.setIcon(icons.icon("pen"))
        self.btn_copy.setIcon(icons.icon("copy"))
        self.btn_delete.setIcon(icons.icon("trash"))
        buttons = QHBoxLayout()
        for b in (self.btn_save, self.btn_edit, self.btn_copy, self.btn_delete):
            buttons.addWidget(b)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(6, 10, 10, 10)
        right_l.addWidget(self.preview, 3)
        right_l.addWidget(self.meta)
        right_l.addLayout(form)
        right_l.addWidget(QLabel(tr("Recognized text")))
        right_l.addWidget(self.ocr_view, 2)
        right_l.addLayout(buttons)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([800, 480])
        self.setCentralWidget(split)

        # Suche mit kurzer Verzögerung
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        self.tag_box.currentIndexChanged.connect(lambda _i: self.reload())

        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self.paste_from_clipboard)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

        self._reload_tags()
        self.reload()

    # --- Laden ---------------------------------------------------------
    def _reload_tags(self) -> None:
        current = self.tag_box.currentData() or ""
        self.tag_box.blockSignals(True)
        self.tag_box.clear()
        self.tag_box.addItem(tr("All tags"), "")
        for tag, count in self.store.tag_counts():
            self.tag_box.addItem(f"{tag}  ({count})", tag)
        idx = self.tag_box.findData(current)
        self.tag_box.setCurrentIndex(max(0, idx))
        self.tag_box.blockSignals(False)

    def reload(self, select_id: int | None = None) -> None:
        self._save_if_modified()
        keep = select_id if select_id is not None else (self._current.id if self._current else None)
        results = self.store.search(self.search.text(), self.tag_box.currentData() or "")
        self.list.blockSignals(True)
        self.list.clear()
        target = None
        for idea in results:
            item = QListWidgetItem(idea.title or tr("(untitled)"))
            thumb = idea.thumb_path if idea.thumb_path.exists() else idea.image_path
            item.setIcon(QIcon(QPixmap(str(thumb))))
            item.setData(Qt.ItemDataRole.UserRole, idea.id)
            item.setToolTip(idea.note or idea.title)
            self.list.addItem(item)
            if idea.id == keep:
                target = item
        self.list.blockSignals(False)
        if target is None and results:
            target = self.list.item(0)
        if target is not None:
            self.list.setCurrentItem(target)
            self._show(self.store.get(target.data(Qt.ItemDataRole.UserRole)))
        else:
            self._show(None)
        total = len(self.store.search())
        self.statusBar().showMessage(tr("{shown} of {total} ideas").format(shown=len(results), total=total))

    def _on_select(self, item: QListWidgetItem | None, _prev) -> None:
        self._save_if_modified()
        self._show(self.store.get(item.data(Qt.ItemDataRole.UserRole)) if item else None)

    def _show(self, idea: Idea | None) -> None:
        self._current = idea
        enabled = idea is not None
        for w in (self.title, self.tags, self.source, self.note, self.btn_save, self.btn_edit,
                  self.btn_copy, self.btn_delete):
            w.setEnabled(enabled)
        if idea is None:
            self.preview.set_image(None)
            self.title.clear()
            self.tags.clear()
            self.source.clear()
            self.note.clear()
            self.ocr_view.clear()
            self.meta.setText(tr("No ideas yet – take a screenshot and click “Save idea”."))
            return
        self.preview.set_image(QPixmap(str(idea.image_path)))
        self.title.setText(idea.title)
        self.tags.setText(idea.tags.replace(",", ", "))
        self.source.setText(idea.source)
        self.note.setPlainText(idea.note)
        self.ocr_view.setPlainText(idea.ocr_text)
        self.meta.setText(tr("Saved on {date}").format(date=idea.created.replace('T', ' ')))

    # --- Aktionen ------------------------------------------------------
    def _modified(self) -> bool:
        c = self._current
        if c is None:
            return False
        return (self.title.text().strip() != c.title
                or ideas.normalize_tags(self.tags.text()) != c.tags
                or self.source.text().strip() != c.source
                or self.note.toPlainText().strip() != c.note)

    def _save_if_modified(self) -> None:
        if self._modified():
            self.save_current(quiet=True)

    def save_current(self, quiet: bool = False) -> None:
        if self._current is None:
            return
        self.store.update(self._current.id, self.title.text(), self.tags.text(),
                          self.note.toPlainText(), self.source.text())
        self._current = self.store.get(self._current.id)
        if not quiet:
            self.statusBar().showMessage(tr("Saved"), 3000)
            self._reload_tags()
            self.reload(self._current.id if self._current else None)

    def edit_image(self) -> None:
        if self._current is None:
            return
        img = QImage(str(self._current.image_path))
        if not img.isNull():
            self.open_editor(img, self._current.id)

    def copy_image(self) -> None:
        if self._current is None:
            return
        img = QImage(str(self._current.image_path))
        from PySide6.QtCore import QBuffer, QIODevice

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        if not system.clipboard_set(bytes(buf.data().data()), "image/png"):
            QGuiApplication.clipboard().setImage(img)
            system.request_keepalive()
        self.statusBar().showMessage(tr("Image copied"), 3000)

    def delete_current(self) -> None:
        if self._current is None:
            return
        answer = QMessageBox.question(
            self, tr("Delete idea"), tr("Delete “{title}” permanently?").format(title=self._current.title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(self._current.id)
        self._current = None
        self._reload_tags()
        self.reload()

    def _open_source(self) -> None:
        text = self.source.text().strip()
        if text:
            QDesktopServices.openUrl(QUrl.fromUserInput(text))

    def paste_from_clipboard(self) -> None:
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            self.statusBar().showMessage(tr("There is no image on the clipboard."), 4000)
            return
        dlg = IdeaDialog(img, self, known_tags=[t for t, _ in self.store.tag_counts()])
        if dlg.exec() != IdeaDialog.DialogCode.Accepted:
            return
        new_id = self.store.add(img, **dlg.values())
        ideas.start_ocr_index(self.store, new_id, self.langs)
        self._reload_tags()
        self.reload(new_id)
