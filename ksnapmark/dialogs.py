"""Kleine Dialoge: Idee speichern, erkannten Text anzeigen."""

from __future__ import annotations

from .i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from . import system


class IdeaDialog(QDialog):
    def __init__(self, image: QImage, parent=None, idea=None, known_tags=None, source_hint=""):
        super().__init__(parent)
        self.setWindowTitle(tr("Save idea"))
        self.setMinimumWidth(720)

        preview = QLabel()
        preview.setFixedSize(300, 220)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("background:#16171a; border-radius:8px;")
        pm = QPixmap.fromImage(image).scaled(
            296, 216, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        preview.setPixmap(pm)

        self.title = QLineEdit(idea.title if idea else "")
        self.title.setPlaceholderText(tr("Short title (optional)"))
        self.tags = QLineEdit(idea.tags.replace(",", ", ") if idea else "")
        self.tags.setPlaceholderText(tr("e.g. design, landing page, inspiration"))
        self.source = QLineEdit(idea.source if idea else source_hint)
        self.source.setPlaceholderText(tr("Link to the source (optional)"))
        self.note = QPlainTextEdit(idea.note if idea else "")
        self.note.setPlaceholderText(tr("What do you like about it? What do you want to do with it?"))
        self.note.setFixedHeight(90)

        form = QFormLayout()
        form.addRow(tr("Title"), self.title)
        form.addRow("Tags", self.tags)
        form.addRow(tr("Source"), self.source)
        form.addRow(tr("Note"), self.note)

        right = QVBoxLayout()
        right.addLayout(form)
        if known_tags:
            hint = QLabel(tr("Known tags: ") + ", ".join(known_tags[:12]))
            hint.setProperty("muted", True)
            hint.setWordWrap(True)
            right.addWidget(hint)

        self.replace_box: QCheckBox | None = None
        if idea is not None:
            self.replace_box = QCheckBox(tr("Update existing idea (instead of creating a new one)"))
            self.replace_box.setChecked(True)
            right.addWidget(self.replace_box)

        buttons = QDialogButtonBox()
        save = buttons.addButton(tr("Save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save.setDefault(True)
        buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(preview, 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(right, 1)
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(buttons)
        self.title.setFocus()

    def values(self) -> dict:
        return {"title": self.title.text(), "tags": self.tags.text(),
                "note": self.note.toPlainText(), "source": self.source.text()}

    def replace_existing(self) -> bool:
        return bool(self.replace_box and self.replace_box.isChecked())


class OcrDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Recognized text"))
        self.resize(560, 400)
        self.edit = QPlainTextEdit(text)
        self.info = QLabel(tr("{n} characters recognized – you can adjust the text before copying.").format(n=len(text)))
        self.info.setProperty("muted", True)

        copy_btn = QPushButton(tr("Copy"))
        copy_btn.setDefault(True)
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        row.addWidget(copy_btn)
        root = QVBoxLayout(self)
        root.addWidget(self.edit, 1)
        root.addWidget(self.info)
        root.addLayout(row)

    def _copy(self) -> None:
        text = self.edit.toPlainText()
        if not system.clipboard_set_text(text):
            QGuiApplication.clipboard().setText(text)
            system.request_keepalive()
        self.info.setText(tr("Copied to clipboard."))
        self.accept()


class QrDialog(QDialog):
    """Ergebnis der QR-/Strichcode-Erkennung."""

    def __init__(self, codes, parent=None):
        super().__init__(parent)
        from . import qr

        self.setWindowTitle(tr("Codes found"))
        self.resize(560, 320)
        root = QVBoxLayout(self)
        self._edits: list[tuple[QPlainTextEdit, object]] = []
        for code in codes:
            head = QLabel(f"{code.kind}")
            head.setProperty("muted", True)
            edit = QPlainTextEdit(qr.describe(code))
            edit.setReadOnly(True)
            edit.setMaximumHeight(110 if len(codes) > 1 else 200)
            root.addWidget(head)
            root.addWidget(edit)
            row = QHBoxLayout()
            row.addStretch(1)
            wifi = qr.parse_wifi(code.data)
            if wifi and wifi.get(tr("Password")):
                pw = QPushButton(tr("Copy password"))
                pw.clicked.connect(lambda _=False, v=wifi[tr("Password")]: self._copy(v))
                row.addWidget(pw)
            if qr.is_url(code.data):
                op = QPushButton(tr("Open link"))
                op.setToolTip(code.data)
                op.clicked.connect(lambda _=False, u=code.data.strip(): system.open_path(u))
                row.addWidget(op)
            cp = QPushButton(tr("Copy"))
            cp.clicked.connect(lambda _=False, v=code.data: self._copy(v))
            row.addWidget(cp)
            root.addLayout(row)
        self.info = QLabel(tr("Links are opened only after you click – check where they lead first."))
        self.info.setProperty("muted", True)
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _copy(self, text: str) -> None:
        if not system.clipboard_set_text(text):
            QGuiApplication.clipboard().setText(text)
            system.request_keepalive()
        self.info.setText(tr("Copied to clipboard."))


EFFECTS = [("blur", tr("Blur")), ("pixel", tr("Pixelate")), ("redact", tr("Redact"))]


class AutoRedactDialog(QDialog):
    """Begriffe/Namen eingeben, Effekt wählen – KSnapMark sucht sie per Texterkennung im Bild."""

    def __init__(self, parent=None, terms: str = "", kind: str = "blur", patterns: bool = True,
                 parts: bool = True, saved: str = "", use_saved: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Auto-redact sensitive data"))
        self.setMinimumWidth(480)

        intro = QLabel(tr("Names or terms that must not be visible in the image – one per line. KSnapMark finds them via OCR (upper/lower case, umlauts and small reading errors do not matter)."))
        intro.setWordWrap(True)
        intro.setProperty("muted", True)

        self.terms = QPlainTextEdit(terms)
        self.terms.setPlaceholderText(tr("e.g.\nJohn Smith\nSmith Ltd\nCustomer 4711"))
        self.terms.setFixedHeight(110)

        self.kind = QComboBox()
        for key, label in EFFECTS:
            self.kind.addItem(label, key)
        idx = self.kind.findData(kind)
        self.kind.setCurrentIndex(idx if idx >= 0 else 0)

        self.parts = QCheckBox(tr("Also find parts of names (e.g. the surname only)"))
        self.parts.setChecked(parts)
        self.patterns = QCheckBox(tr("Also typical sensitive data (e-mail, IBAN, IP, phone, token …)"))
        self.patterns.setChecked(patterns)

        form = QFormLayout()
        form.addRow(tr("Effect"), self.kind)

        # Optional: dauerhafte Liste (z. B. eigener Name, Firma) – standardmäßig aus
        self.use_saved = QCheckBox(tr("Use persistent list (searched on every capture)"))
        self.use_saved.setChecked(use_saved)
        self.saved = QPlainTextEdit(saved)
        self.saved.setPlaceholderText(tr("Always redact, one per line, e.g. your name or your company"))
        self.saved.setFixedHeight(80)
        self.saved.setVisible(use_saved)
        self.saved_hint = QLabel(tr("Stored unencrypted in ~/.config/ksnapmark/redact_terms.txt (readable only by you)."))
        self.saved_hint.setWordWrap(True)
        self.saved_hint.setProperty("muted", True)
        self.saved_hint.setVisible(use_saved)

        def toggle(on: bool) -> None:
            self.saved.setVisible(on)
            self.saved_hint.setVisible(on)
            self.adjustSize()

        self.use_saved.toggled.connect(toggle)

        note = QLabel(tr("After applying, KSnapMark checks via OCR whether anything is still readable and additionally redacts such spots."))
        note.setWordWrap(True)
        note.setProperty("muted", True)

        buttons = QDialogButtonBox()
        go = buttons.addButton(tr("Apply"), QDialogButtonBox.ButtonRole.AcceptRole)
        go.setDefault(True)
        buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._check_and_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(self.terms)
        root.addLayout(form)
        root.addWidget(self.parts)
        root.addWidget(self.patterns)
        root.addWidget(self.use_saved)
        root.addWidget(self.saved)
        root.addWidget(self.saved_hint)
        root.addWidget(note)
        root.addWidget(buttons)
        self.terms.setFocus()

    def _all_terms(self) -> list[str]:
        from .findtext import parse_terms

        raw = self.terms.toPlainText()
        if self.use_saved.isChecked():
            raw += "\n" + self.saved.toPlainText()
        return parse_terms(raw)

    def _check_and_accept(self) -> None:
        if not self._all_terms() and not self.patterns.isChecked():
            self.terms.setFocus()
            return  # nichts zu suchen
        self.accept()

    def values(self) -> dict:
        return {"raw": self.terms.toPlainText(), "terms": self._all_terms(),
                "kind": self.kind.currentData(), "parts": self.parts.isChecked(),
                "patterns": self.patterns.isChecked(),
                "use_saved": self.use_saved.isChecked(), "saved_raw": self.saved.toPlainText()}


class FrameDialog(QDialog):
    """Background, padding, rounded corners and shadow around the image, with a live preview."""

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox

        from .frame import BACKGROUNDS

        self.setWindowTitle(tr("Frame and shadow"))
        self._image = image.scaled(360, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self._scale = self._image.width() / max(1, image.width())
        self.preview = QLabel()
        self.preview.setMinimumSize(420, 300)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#16171a; border-radius:8px;")

        self.background = QComboBox()
        for key, (label, _c1, _c2) in BACKGROUNDS.items():
            self.background.addItem(label, key)
        self.padding = QSpinBox()
        self.padding.setRange(0, 400)
        self.padding.setValue(48)
        self.padding.setSuffix(" px")
        self.radius = QSpinBox()
        self.radius.setRange(0, 100)
        self.radius.setValue(12)
        self.radius.setSuffix(" px")
        self.shadow = QCheckBox(tr("Soft shadow"))
        self.shadow.setChecked(True)

        form = QFormLayout()
        form.addRow(tr("Background"), self.background)
        form.addRow(tr("Padding"), self.padding)
        form.addRow(tr("Corner radius"), self.radius)
        form.addRow("", self.shadow)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addWidget(self.preview)
        root.addLayout(form)
        root.addWidget(buttons)
        for w in (self.background,):
            w.currentIndexChanged.connect(self._update)
        for w in (self.padding, self.radius):
            w.valueChanged.connect(self._update)
        self.shadow.toggled.connect(self._update)
        self._update()

    def options(self) -> dict:
        return {"padding": self.padding.value(), "background": self.background.currentData(),
                "radius": self.radius.value(), "shadow": self.shadow.isChecked()}

    def _update(self) -> None:
        from .frame import add_frame

        o = self.options()
        s = self._scale
        framed = add_frame(self._image, padding=round(o["padding"] * s), background=o["background"],
                           radius=round(o["radius"] * s), shadow=o["shadow"])
        self.preview.setPixmap(QPixmap.fromImage(framed).scaled(
            self.preview.width() - 8, self.preview.height() - 8, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
