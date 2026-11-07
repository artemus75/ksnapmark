"""Einstellungsdialog (schreibt ~/.config/ksnapmark/config.toml)."""

from __future__ import annotations

from .i18n import tr

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout)

from . import config, system
from .i18n import SUPPORTED

BACKEND_LABELS = {
    "auto": tr("Automatic (recommended)"),
    "kwin": tr("KWin interface (KDE)"),
    "portal": tr("Desktop portal"),
    "spectacle": "Spectacle",
    "grim": "grim",
    "gnome-screenshot": "gnome-screenshot",
    "maim": "maim",
    "scrot": "scrot",
    "import": "ImageMagick (import)",
}


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, cfg: config.Config, history=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._history = history
        self.setWindowTitle(tr("KSnapMark – Settings"))
        self.setMinimumWidth(620)

        self.save_dir = QLineEdit(str(cfg.save_dir))
        browse = QPushButton(tr("Browse …"))
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.save_dir, 1)
        dir_row.addWidget(browse)

        self.ocr_langs = QLineEdit(cfg.ocr_langs)
        self.ocr_langs.setPlaceholderText(tr("e.g. deu+eng"))
        from . import ocr

        installed = ocr.installed_langs()
        self.ocr_hint = QLabel(tr("Installed: ") + (", ".join(installed) if installed else tr("Tesseract not found")))
        self.ocr_hint.setProperty("muted", True)
        self.ocr_hint.setWordWrap(True)

        self.backend = QComboBox()
        for key, label in BACKEND_LABELS.items():
            self.backend.addItem(label, key)
        idx = self.backend.findData(cfg.capture_backend)
        self.backend.setCurrentIndex(idx if idx >= 0 else 0)

        self.resident = QCheckBox(tr("Keep running in the background (tray icon, fast start)"))
        self.resident.setChecked(cfg.resident)
        self.autostart = QCheckBox(tr("Start automatically at login"))
        self.autostart.setChecked(system.autostart_enabled())

        self.snap = QCheckBox(tr("Snap to windows (KDE Plasma only: click a window instead of dragging)"))
        self.snap.setChecked(cfg.snap_windows)

        self.cursor = QCheckBox(tr("Include the mouse pointer in screenshots (not with the desktop portal)"))
        self.cursor.setChecked(cfg.include_cursor)
        self.auto_copy = QCheckBox(tr("Copy new screenshots to the clipboard automatically"))
        self.auto_copy.setChecked(cfg.auto_copy)
        self.loupe = QCheckBox(tr("Show the magnifier with color value while selecting (toggle with L)"))
        self.loupe.setChecked(cfg.show_loupe)

        self.history = QCheckBox(tr("Keep a history of the latest captures"))
        self.history.setChecked(cfg.history)
        self.history_size = QSpinBox()
        self.history_size.setRange(1, 50)
        self.history_size.setValue(max(1, cfg.history_size))
        self.history_size.setEnabled(cfg.history)
        self.history.toggled.connect(self.history_size.setEnabled)
        self.history_ocr = QCheckBox(tr("Index the text of history images for the search (OCR, stays on this computer)"))
        self.history_ocr.setChecked(cfg.history_ocr)
        clear = QPushButton(tr("Clear history now"))
        clear.clicked.connect(self._clear_history)
        hist_row = QHBoxLayout()
        hist_row.addWidget(self.history_size)
        hist_row.addWidget(QLabel(tr("entries")))
        hist_row.addStretch(1)
        hist_row.addWidget(clear)
        hist_note = QLabel(tr("The history is stored as image files in ~/.local/share/ksnapmark/history (readable only by you)."))
        hist_note.setProperty("muted", True)
        hist_note.setWordWrap(True)

        self.record_dir = QLineEdit(cfg.record_dir)
        self.record_format = QComboBox()
        self.record_format.addItem(tr("WebM (small, default)"), "webm")
        self.record_format.addItem(tr("MP4 (plays everywhere)"), "mp4")
        self.record_format.setCurrentIndex(max(0, self.record_format.findData(cfg.record_format)))
        self.record_gif = QCheckBox(tr("Also save screen recordings as GIF (needs ffmpeg)"))
        self.record_gif.setChecked(cfg.record_gif)

        self.upload_url = QLineEdit(cfg.upload_url)
        self.upload_hours = QSpinBox()
        self.upload_hours.setRange(1, 24 * 365)
        self.language = QComboBox()
        self.language.addItem(tr("Automatic (system language)"), "auto")
        for code, native in SUPPORTED.items():
            self.language.addItem(native, code)
        idx = self.language.findData(cfg.language)
        self.language.setCurrentIndex(idx if idx >= 0 else 0)

        self.upload_hours.setValue(cfg.upload_expires_hours)
        self.upload_hours.setSuffix(tr(" hours"))

        form = QFormLayout()
        form.addRow(tr("Save folder"), dir_row)
        form.addRow(tr("Text recognition"), self.ocr_langs)
        form.addRow("", self.ocr_hint)
        form.addRow(tr("Language"), self.language)
        form.addRow(tr("Capture method"), self.backend)
        form.addRow("", self.resident)
        form.addRow("", self.autostart)
        form.addRow("", self.snap)
        form.addRow("", self.cursor)
        form.addRow("", self.auto_copy)
        form.addRow("", self.loupe)
        form.addRow("", self.history)
        form.addRow("", self.history_ocr)
        form.addRow(tr("History size"), hist_row)
        form.addRow("", hist_note)
        form.addRow(tr("Save videos in"), self.record_dir)
        form.addRow(tr("Video format"), self.record_format)
        form.addRow("", self.record_gif)
        form.addRow(tr("Upload address (0x0.st or compatible server)"), self.upload_url)
        form.addRow(tr("Link valid for"), self.upload_hours)

        buttons = QDialogButtonBox()
        ok = buttons.addButton(tr("Save"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose save folder"), self.save_dir.text())
        if d:
            self.save_dir.setText(d)

    def _clear_history(self) -> None:
        if self._history is not None:
            n = self._history.clear()
            QMessageBox.information(self, tr("History"), tr("{n} entry/entries deleted.").format(n=n))

    def new_config(self) -> config.Config:
        return config.Config(
            save_dir=Path(self.save_dir.text().strip() or "~/Pictures/Screenshots").expanduser(),
            ocr_langs=self.ocr_langs.text().strip() or "deu+eng",
            upload_url=self.upload_url.text().strip() or "https://0x0.st",
            upload_expires_hours=self.upload_hours.value(),
            capture_backend=self.backend.currentData(),
            resident=self.resident.isChecked(),
            history=self.history.isChecked(),
            history_size=self.history_size.value(),
            history_ocr=self.history_ocr.isChecked(),
            snap_windows=self.snap.isChecked(),
            include_cursor=self.cursor.isChecked(),
            show_loupe=self.loupe.isChecked(),
            auto_copy=self.auto_copy.isChecked(),
            record_dir=self.record_dir.text().strip() or "~/Videos",
            record_format=self.record_format.currentData(),
            record_gif=self.record_gif.isChecked(),
            language=self.language.currentData())

    def _save(self) -> None:
        new = self.new_config()
        if not new.upload_url.lower().startswith("https://"):
            QMessageBox.warning(self, tr("Upload address"), tr("The upload address must start with https://."))
            return
        try:
            config.save(new)
        except OSError as exc:
            QMessageBox.warning(self, tr("Save"), tr("Settings could not be saved:\n{exc}").format(exc=exc))
            return
        if self.autostart.isChecked() != system.autostart_enabled():
            if not system.set_autostart(self.autostart.isChecked()):
                QMessageBox.warning(self, "Autostart", tr("The autostart entry could not be changed."))
        restart = new.resident != self.cfg.resident or new.language != self.cfg.language
        for field in new.__dataclass_fields__:
            setattr(self.cfg, field, getattr(new, field))  # laufende Instanz sofort aktualisieren
        self.saved.emit()
        if restart:
            QMessageBox.information(self, tr("Settings"),
                                    tr("Background mode and language change only after KSnapMark is restarted (tray menu → Quit, then start it again)."))
        self.accept()
