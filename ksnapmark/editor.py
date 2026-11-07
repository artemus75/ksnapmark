"""Editor-Fenster: Bild bearbeiten, kopieren, speichern, teilen, Text auslesen, Idee ablegen."""

from __future__ import annotations

from .i18n import tr

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSettings, QSize, Qt
from PySide6.QtGui import (QAction, QActionGroup, QColor, QGuiApplication, QImage, QKeySequence,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QFileDialog,
                               QFrame, QLabel, QMainWindow, QMenu, QMessageBox, QScrollArea,
                               QSizePolicy, QSlider, QToolBar, QToolButton, QWidget)

from . import findtext, ideas, ocr, qr, sensitive, system
from .asyncutil import run_async
from .canvas import Canvas
from .dialogs import AutoRedactDialog, IdeaDialog, OcrDialog, QrDialog
from .icons import app_icon, icon

TOOLS = [
    ("select", tr("Select / edit (move, resize, recolor, delete with Del)"), "V"),
    None,
    ("pen", tr("Pen"), "P"),
    ("marker", tr("Highlighter"), "M"),
    ("arrow", tr("Arrow"), "A"),
    ("line", tr("Line"), "L"),
    ("rect", tr("Rectangle"), "R"),
    ("ellipse", "Ellipse", "E"),
    ("text", "Text", "T"),
    ("number", tr("Numbering"), "N"),
    None,
    ("blur", tr("Blur"), "B"),
    ("pixel", tr("Pixelate (mosaic)"), "K"),
    ("redact", tr("Redact (solid)"), "X"),
    ("spot", tr("Spotlight (dims everything outside)"), "S"),
    None,
    ("crop", tr("Crop"), "C"),
    None,
    ("pick", tr("Color picker (takes a color from the image; copies the hex value)"), "I"),
]

PALETTE = ["#ff2d2d", "#ff9500", "#ffd60a", "#30d158", "#0a84ff", "#bf5af2", "#ffffff", "#000000"]


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data().data())


class EditorWindow(QMainWindow):
    def __init__(self, image: QImage, dpr: float, ctx, idea_id: int | None = None,
                 history_name: str | None = None, record: bool = True):
        super().__init__()
        self.ctx = ctx
        # Verlauf: jede Aufnahme einmal ablegen, beim Kopieren/Speichern durch die bearbeitete Fassung ersetzen
        self.hist_name = history_name
        if record and history_name is None and idea_id is None:
            self.hist_name = ctx.history.add(image)
        self.idea_id = idea_id
        self.last_path: Path | None = None
        self._dirty = False
        self._auto_copied = False   # clipboard holds the untouched capture (set on start)
        self._settings = QSettings("ksnapmark", "ksnapmark")

        self.setWindowIcon(app_icon())
        self.setWindowTitle(f"KSnapMark – {image.width()} × {image.height()}")

        self._syncing = False
        self.canvas = Canvas(image, dpr)
        self.canvas.selection_changed.connect(self._on_selection)
        self.canvas.changed.connect(self._on_canvas_changed)
        self.canvas.message.connect(lambda m: self.statusBar().showMessage(m, 4000))
        self.canvas.picked.connect(self._on_picked)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(self.scroll)

        # Reihenfolge: zuerst hinzugefügte Leiste liegt unten -> Aktionen unten, Werkzeuge direkt unter dem Bild
        self._build_actions_bar()
        self.addToolBarBreak(Qt.ToolBarArea.BottomToolBarArea)
        self._build_tools_bar()
        self._build_shortcuts()
        self._restore_settings()
        self._on_canvas_changed(initial=True)
        self._fit_initial()
        self.statusBar().showMessage(
            tr("Enter: copy & close  ·  Ctrl+S: save  ·  Esc: close  ·  Ctrl+wheel: zoom"), 8000)
        if record and history_name is None and idea_id is None and ctx.cfg.auto_copy:
            self._auto_copy(image)

    def _auto_copy(self, image: QImage) -> None:
        """A fresh capture is in the clipboard immediately; editing needs a new Copy."""
        if system.clipboard_set(png_bytes(image), "image/png"):
            pass
        else:
            QGuiApplication.clipboard().setImage(image)
            system.request_keepalive()
        self._auto_copied = True
        self.statusBar().showMessage(
            tr("Screenshot is already in the clipboard  ·  Enter: copy & close  ·  Ctrl+S: save  ·  Esc: close"), 10000)

    # --- Aufbau ----------------------------------------------------------
    def _build_tools_bar(self) -> None:
        bar = QToolBar(tr("Tools"))
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(22, 22))
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)
        self.tool_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for entry in TOOLS:
            if entry is None:
                bar.addSeparator()
                continue
            name, label, key = entry
            act = QAction(icon(name), label, self)
            act.setCheckable(True)
            act.setShortcut(QKeySequence(key))
            act.setToolTip(f"{label} ({key})")
            act.triggered.connect(lambda _c=False, n=name: self.set_tool(n))
            group.addAction(act)
            bar.addAction(act)
            self.tool_actions[name] = act
        bar.addSeparator()

        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        self.swatches: dict[str, QToolButton] = {}
        for col in PALETTE:
            btn = self._swatch(col)
            bar.addWidget(btn)
        custom = QToolButton()
        custom.setText("…")
        custom.setToolTip(tr("Choose a custom color"))
        custom.clicked.connect(self._pick_custom_color)
        bar.addWidget(custom)
        bar.addSeparator()

        label = QLabel(tr("Size"))
        label.setProperty("muted", True)
        bar.addWidget(label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 24)
        self.slider.setFixedWidth(120)
        self.slider.setToolTip(tr("Stroke width / font size / effect strength"))
        self.slider.valueChanged.connect(self._on_width)
        bar.addWidget(self.slider)
        self.fill_box = QCheckBox(tr("Filled"))
        self.fill_box.setToolTip(tr("Fill rectangles and ellipses"))
        self.fill_box.toggled.connect(self._on_filled)
        bar.addWidget(self.fill_box)

    def _swatch(self, color: str) -> QToolButton:
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setProperty("swatch", True)
        btn.setStyleSheet(f"QToolButton {{ background: {color}; }}")
        btn.setToolTip(color)
        btn.clicked.connect(lambda _c=False, c=color: self.set_color(c))
        self.color_group.addButton(btn)
        self.swatches[color] = btn
        return btn

    def _build_actions_bar(self) -> None:
        bar = QToolBar(tr("Actions"))
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)

        self.act_auto = QAction(icon("wand"), tr("Auto-redact"), self)
        self.act_auto.setToolTip(tr("Find names/terms and typical sensitive data via OCR and redact them (Ctrl+Shift+R)"))
        self.act_auto.triggered.connect(self.auto_redact)
        self.act_ocr = QAction(icon("ocr"), tr("Read text"), self)
        self.act_ocr.setToolTip(tr("Recognize text in the image (Ctrl+T)"))
        self.act_ocr.triggered.connect(self.do_ocr)
        self.act_qr = QAction(icon("qr"), tr("Read QR"), self)
        self.act_qr.setToolTip(tr("Read QR codes and barcodes in the image (Ctrl+Shift+Q)"))
        self.act_qr.triggered.connect(self.read_qr)
        self.act_pin = QAction(icon("pin"), tr("Pin"), self)
        self.act_pin.setToolTip(tr("Pin the image as a floating window above the desktop (Ctrl+P)"))
        self.act_pin.triggered.connect(self.pin_image)
        self.act_idea = QAction(icon("idea"), tr("Save idea"), self)
        self.act_idea.setToolTip(tr("Put into the ideas collection (Ctrl+I)"))
        self.act_idea.triggered.connect(self.save_idea)
        for a in (self.act_auto, self.act_ocr, self.act_qr, self.act_pin, self.act_idea):
            bar.addAction(a)

        spacer = QWidget()
        spacer.setObjectName("spacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        self.act_undo = QAction(icon("undo"), "", self)
        self.act_undo.setToolTip(tr("Undo (Ctrl+Z)"))
        self.act_undo.triggered.connect(self.canvas.undo)
        self.act_redo = QAction(icon("redo"), "", self)
        self.act_redo.setToolTip(tr("Redo (Ctrl+Y)"))
        self.act_redo.triggered.connect(self.canvas.redo)
        bar.addAction(self.act_undo)
        bar.addAction(self.act_redo)
        self.act_frame = QAction(icon("frame"), tr("Frame"), self)
        self.act_frame.setToolTip(tr("Add background, rounded corners and shadow"))
        self.act_frame.triggered.connect(self.add_frame)
        bar.addAction(self.act_frame)
        bar.addSeparator()

        share = QToolButton()
        share.setText(tr("Share"))
        share.setIcon(icon("share"))
        share.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        share.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(share)
        menu.addAction(tr("Copy image"), self.copy_image)
        menu.addAction(tr("Copy file path"), self.copy_path)
        menu.addSeparator()
        menu.addAction(tr("Send by e-mail …"), self.share_email)
        menu.addAction(tr("Open with another program …"), self.share_open_with)
        menu.addSeparator()
        up = menu.addMenu(tr("Upload (public link)"))
        from .uploaders import targets

        for t in targets(self.ctx.cfg.upload_url):
            up.addAction(t.label, lambda k=t.key: self.share_upload(k))
        share.setMenu(menu)
        bar.addWidget(share)

        self.act_save = QAction(icon("save"), tr("Save"), self)
        self.act_save.setToolTip(tr("Save (Ctrl+S)"))
        self.act_save.triggered.connect(self.save_quick)
        save_btn = QToolButton()
        save_btn.setDefaultAction(self.act_save)
        save_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        save_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        save_menu = QMenu(save_btn)
        save_menu.addAction(tr("Save as …"), self.save_as)
        save_btn.setMenu(save_menu)
        bar.addWidget(save_btn)

        self.act_copy = QAction(icon("copy"), tr("Copy"), self)
        self.act_copy.setToolTip(tr("Copy to clipboard (Ctrl+C) – Enter copies and closes"))
        self.act_copy.triggered.connect(self.copy_image)
        bar.addAction(self.act_copy)

        self.act_close = QAction(icon("close"), "", self)
        self.act_close.setToolTip(tr("Close (Esc)"))
        self.act_close.triggered.connect(self.close)
        bar.addAction(self.act_close)

    def _build_shortcuts(self) -> None:
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)

        sc("Ctrl+Z", self.canvas.undo)
        sc("Ctrl+Y", self.canvas.redo)
        sc("Ctrl+Shift+Z", self.canvas.redo)
        sc("Ctrl+C", self.copy_image)
        sc("Ctrl+S", self.save_quick)
        sc("Ctrl+Shift+S", self.save_as)
        sc("Ctrl+T", self.do_ocr)
        sc("Ctrl+I", self.save_idea)
        sc("Ctrl+P", self.pin_image)
        sc("Ctrl+Shift+Q", self.read_qr)
        sc("Ctrl+Shift+R", self.auto_redact)
        sc("Return", lambda: self.copy_image(close=True))
        sc("Enter", lambda: self.copy_image(close=True))
        sc("Esc", self._escape)

    def _restore_settings(self) -> None:
        tool = str(self._settings.value("tool", "arrow"))
        color = str(self._settings.value("color", PALETTE[0]))
        width = int(self._settings.value("width", 6))
        filled = str(self._settings.value("filled", "false")) == "true"
        if tool not in self.tool_actions:
            tool = "arrow"
        self.slider.setValue(width)
        self.fill_box.setChecked(filled)
        self.tool_actions[tool].setChecked(True)
        self.set_tool(tool)
        self.set_color(color)

    def _fit_initial(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        lw, lh = self.canvas.logical_size()
        zoom = min(1.0, (avail.width() * 0.92 - 24) / lw, (avail.height() * 0.9 - 230) / lh)
        self.canvas.zoom = max(0.1, zoom)
        self.canvas._relayout()
        w = min(max(1080, int(lw * self.canvas.zoom) + 40), avail.width())
        h = min(int(lh * self.canvas.zoom) + 230, avail.height())
        self.resize(w, max(h, 300))

    # --- Werkzeug-Zustand -------------------------------------------------------
    def _escape(self) -> None:
        """Esc: first clear the selection, then close."""
        if self.canvas.selected is not None:
            self.canvas.deselect()
        else:
            self.close()

    def _on_filled(self, value: bool) -> None:
        self.canvas.filled = value
        if not self._syncing:
            self.canvas.apply_to_selected(filled=value)

    def _on_selection(self, item) -> None:
        """A drawn item was selected: show its color/size in the toolbar (without changing it)."""
        if item is None:
            return
        self._syncing = True
        try:
            self.set_color(item.color, apply=False)
            self.slider.blockSignals(True)
            self.slider.setValue(max(1, min(24, round(item.width / self.canvas.dpr))))
            self.slider.blockSignals(False)
            self.canvas.width = self.slider.value()
            if item.kind in ("rect", "ellipse"):
                self.fill_box.blockSignals(True)
                self.fill_box.setChecked(item.filled)
                self.fill_box.blockSignals(False)
                self.canvas.filled = item.filled
        finally:
            self._syncing = False

    def set_tool(self, name: str) -> None:
        self.canvas.set_tool(name)
        self.tool_actions[name].setChecked(True)
        self._settings.setValue("tool", name)

    def _on_picked(self, color: str) -> None:
        """Pipette: Farbe als Zeichenfarbe übernehmen und den Hex-Wert in die Zwischenablage legen."""
        self.set_color(color)
        if system.clipboard_set_text(color.upper()):
            self.statusBar().showMessage(tr("Color {color} picked and copied").format(color=color.upper()), 6000)
        else:
            self.statusBar().showMessage(tr("Color {color} picked").format(color=color.upper()), 6000)

    def set_color(self, color: str, apply: bool = True) -> None:
        self.canvas.color = color
        if apply and self.canvas.selected is not None:
            self.canvas.apply_to_selected(color=color)
        btn = self.swatches.get(color)
        if btn is not None:
            btn.setChecked(True)
        else:
            checked = self.color_group.checkedButton()
            if checked is not None:
                self.color_group.setExclusive(False)
                checked.setChecked(False)
                self.color_group.setExclusive(True)
        if apply:
            self._settings.setValue("color", color)

    def _pick_custom_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.canvas.color), self, tr("Choose color"))
        if col.isValid():
            self.set_color(col.name())

    def _on_width(self, value: int) -> None:
        self.canvas.width = value
        if not self._syncing:
            self.canvas.apply_to_selected(width=value)
            self._settings.setValue("width", value)

    def _on_canvas_changed(self, initial: bool = False) -> None:
        self.act_undo.setEnabled(self.canvas.can_undo())
        self.act_redo.setEnabled(self.canvas.can_redo())
        self.setWindowTitle(f"KSnapMark – {self.canvas.base.width()} × {self.canvas.base.height()}")
        if not initial:
            self._dirty = True
            if self._auto_copied:
                self._auto_copied = False
                self.statusBar().showMessage(
                    tr("Changed – click Copy (or press Enter) to put the edited version into the clipboard"), 8000)
            self._settings.setValue("filled", "true" if self.canvas.filled else "false")

    # --- Ausgabe ----------------------------------------------------------------
    def current_image(self) -> QImage:
        return self.canvas.result_image()

    def _record_history(self, img: QImage) -> None:
        if self.hist_name is not None:
            self.hist_name = self.ctx.history.add(img, replace=self.hist_name) or self.hist_name

    def copy_image(self, close: bool = False) -> None:
        img = self.current_image()
        if system.clipboard_set(png_bytes(img), "image/png"):
            msg = tr("Copied to clipboard")
        else:
            QGuiApplication.clipboard().setImage(img)
            system.request_keepalive()
            msg = (tr("Copied to clipboard (install wl-clipboard or xclip to keep it after closing)"))
        self._dirty = False
        self._auto_copied = False
        self._record_history(img)
        self.statusBar().showMessage(msg, 5000)
        if close:
            system.notify("KSnapMark", tr("Screenshot copied"))
            self.close()

    def _default_path(self) -> Path:
        return system.unique_screenshot_path(self.ctx.cfg.save_dir)

    def save_quick(self) -> Path | None:
        path = self.last_path or self._default_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, tr("Save"), tr("Folder could not be created:\n{exc}").format(exc=exc))
            return None
        img = self.current_image()
        if not img.save(str(path)):
            QMessageBox.warning(self, tr("Save"), tr("Could not save:\n{path}").format(path=path))
            return None
        self.last_path = path
        self._dirty = False
        self._record_history(img)
        self.statusBar().showMessage(tr("Saved: {path}").format(path=path), 8000)
        return path

    def save_as(self) -> None:
        start = str(self.last_path or self._default_path())
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save as"), start, "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp)")
        if not path:
            return
        if not self.current_image().save(path):
            QMessageBox.warning(self, tr("Save"), tr("Could not save:\n{path}").format(path=path))
            return
        self.last_path = Path(path)
        self._dirty = False
        self.statusBar().showMessage(tr("Saved: {path}").format(path=path), 8000)

    # --- Teilen -----------------------------------------------------------------
    def _temp_file(self) -> str | None:
        # private, unpredictable file name (the shared /tmp is world-writable)
        fd, name = tempfile.mkstemp(prefix="ksnapmark_share_", suffix=".png")
        os.close(fd)
        return name if self.current_image().save(name, "PNG") else None

    def copy_path(self) -> None:
        path = self.save_quick()
        if path is None:
            return
        if not system.clipboard_set_text(str(path)):
            QGuiApplication.clipboard().setText(str(path))
            system.request_keepalive()
        self.statusBar().showMessage(tr("Path copied: {path}").format(path=path), 6000)

    def share_email(self) -> None:
        path = self._temp_file()
        if path and system.email_with_attachment(path):
            self.statusBar().showMessage(tr("Opening e-mail program …"), 5000)
        else:
            QMessageBox.information(self, tr("Share"),
                                    tr("xdg-email was not found (sudo pacman -S xdg-utils)."))

    def add_frame(self) -> None:
        from .dialogs import FrameDialog

        dlg = FrameDialog(self.canvas.result_image(), self)
        if dlg.exec():
            self.canvas.apply_frame(**dlg.options())

    def share_open_with(self) -> None:
        path = self._temp_file()
        if path and system.open_path(path):
            self.statusBar().showMessage(tr("Opening …"), 4000)
        else:
            QMessageBox.information(self, tr("Share"),
                                    tr("xdg-open was not found (sudo pacman -S xdg-utils)."))

    def share_upload(self, key: str | None = None) -> None:
        from .uploaders import target, upload

        cfg = self.ctx.cfg
        tgt = target(key or "0x0", cfg.upload_url)
        note = tgt.note
        if tgt.key == "0x0":
            note = tr("Link valid for {hours} h (if the service supports it).").format(hours=cfg.upload_expires_hours)
        answer = QMessageBox.question(
            self, tr("Upload"),
            tr("The screenshot will be uploaded to {url}. Anyone with the link can see it. {note}\n\nWere sensitive areas redacted?").format(url=tgt.host, note=note),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        path = self._temp_file()
        if path is None:
            return
        self.statusBar().showMessage(tr("Uploading …"))
        run_async(lambda: upload(path, tgt.key, cfg.upload_url, cfg.upload_expires_hours),
                  self._upload_done,
                  lambda msg: QMessageBox.warning(self, tr("Upload"), msg))

    def _upload_done(self, url: str) -> None:
        if not system.clipboard_set_text(url):
            QGuiApplication.clipboard().setText(url)
            system.request_keepalive()
        self.statusBar().showMessage(tr("Link copied: {url}").format(url=url), 10000)
        system.notify("KSnapMark", tr("Link copied: {url}").format(url=url))

    # --- OCR / Auto-Schwärzen -----------------------------------------------------
    def _need_tesseract(self) -> bool:
        if ocr.available():
            return False
        QMessageBox.information(self, tr("Text recognition"), ocr.MISSING_HINT)
        return True

    def do_ocr(self) -> None:
        if self._need_tesseract():
            return
        img = self.canvas.base.copy()
        self.statusBar().showMessage(tr("Recognizing text …"))
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        run_async(lambda: ocr.ocr_text(img, self.ctx.cfg.ocr_langs), self._ocr_done, self._ocr_failed)

    def _ocr_done(self, text: str) -> None:
        QApplication.restoreOverrideCursor()
        if not text.strip():
            self.statusBar().showMessage(tr("No text recognized."), 5000)
            return
        self.statusBar().clearMessage()
        OcrDialog(text, self).exec()

    def pin_image(self) -> None:
        from .pin import PinWindow

        win = PinWindow(self.current_image(), self.canvas.dpr)
        win.open_in_editor.connect(self._open_copy_in_editor)
        self.ctx.keep(win)
        win.show()
        self.statusBar().showMessage(tr("Pinned – double-click the image to close it."), 6000)

    def _open_copy_in_editor(self, img: QImage) -> None:
        win = EditorWindow(img, 1.0, self.ctx, record=False)
        self.ctx.keep(win)
        win.show()

    def read_qr(self) -> None:
        if not qr.available():
            QMessageBox.information(self, tr("Read QR code"), qr.MISSING_HINT)
            return
        img = self.canvas.base.copy()
        self.statusBar().showMessage(tr("Looking for QR codes …"))
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        run_async(lambda: qr.decode(img), self._qr_done, self._ocr_failed)

    def _qr_done(self, codes) -> None:
        QApplication.restoreOverrideCursor()
        if not codes:
            self.statusBar().showMessage(tr("No QR code or barcode found."), 6000)
            return
        self.statusBar().clearMessage()
        QrDialog(codes, self).exec()

    def _ocr_failed(self, message: str) -> None:
        QApplication.restoreOverrideCursor()
        self.statusBar().clearMessage()
        QMessageBox.warning(self, tr("Text recognition"), message)

    def auto_redact(self) -> None:
        if self._need_tesseract():
            return
        st = QSettings("ksnapmark", "ksnapmark")
        dlg = AutoRedactDialog(
            self, getattr(self.ctx, "last_terms", ""),
            str(st.value("autoredact/kind", "blur")),
            str(st.value("autoredact/patterns", "true")).lower() == "true",
            str(st.value("autoredact/parts", "true")).lower() == "true",
            findtext.load_saved(),
            str(st.value("autoredact/use_saved", "false")).lower() == "true")
        if dlg.exec() != AutoRedactDialog.DialogCode.Accepted:
            return
        opts = dlg.values()
        self.ctx.last_terms = opts["raw"]  # nur für diese Sitzung im Speicher, nicht auf der Platte
        st.setValue("autoredact/kind", opts["kind"])
        st.setValue("autoredact/patterns", "true" if opts["patterns"] else "false")
        st.setValue("autoredact/parts", "true" if opts["parts"] else "false")
        st.setValue("autoredact/use_saved", "true" if opts["use_saved"] else "false")
        if opts["use_saved"] and not findtext.save_saved(opts["saved_raw"]):
            QMessageBox.warning(self, "KSnapMark", tr("The persistent list could not be saved."))

        img = self.canvas.base.copy()
        langs = self.ctx.cfg.ocr_langs
        self.statusBar().showMessage(tr("Searching the image …"))
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)

        def job():
            words = ocr.ocr_words(img, langs)
            by_terms = findtext.find_terms(words, opts["terms"], opts["parts"]) if opts["terms"] else []
            found = list(by_terms)
            if opts["patterns"]:
                found += sensitive.find_sensitive(words)
            return {"found": sensitive._dedupe(found),
                    "missing": findtext.missing_terms(opts["terms"], by_terms)}

        run_async(job, lambda res, o=opts: self._redact_done(res, o), self._ocr_failed)

    def _redact_done(self, res: dict, opts: dict) -> None:
        QApplication.restoreOverrideCursor()
        found, missing = res["found"], res["missing"]
        miss_txt = (tr(" Not found: ") + ", ".join(missing) + ".") if missing else ""
        if not found:
            self.statusBar().showMessage(tr("Nothing found.") + miss_txt +
                                         tr(" If necessary, mark them yourself with the blur tool."), 10000)
            return
        kind = opts["kind"]
        self.canvas.add_effects([rect for _label, rect in found], kind, adaptive=True)
        self.statusBar().showMessage(tr("{n} spot(s) processed.{missing} Checking the result …").format(n=len(found), missing=miss_txt), 0)
        if kind == "redact":
            self.statusBar().showMessage(tr("{n} spot(s) redacted.{missing} Undo with Ctrl+Z.").format(n=len(found), missing=miss_txt), 10000)
            return
        # Nachprüfung: ist im bearbeiteten Bild noch etwas maschinenlesbar? Dann zusätzlich schwärzen.
        base_key = self.canvas.base.cacheKey()
        checked = self.canvas.result_image()
        langs = self.ctx.cfg.ocr_langs

        def verify():
            words = ocr.ocr_words(checked, langs)
            left = findtext.find_terms(words, opts["terms"], opts["parts"]) if opts["terms"] else []
            if opts["patterns"]:
                left += sensitive.find_sensitive(words)
            return sensitive._dedupe(left)

        run_async(verify, lambda left, n=len(found), m=miss_txt, k=base_key: self._verify_done(left, n, m, k),
                  lambda _msg, n=len(found), m=miss_txt: self.statusBar().showMessage(
                      tr("{n} spot(s) processed.{m} (verification not possible)").format(n=n, m=m), 10000))

    def _verify_done(self, left, count: int, miss_txt: str, base_key) -> None:
        if self.canvas.base.cacheKey() != base_key:  # inzwischen zugeschnitten: Koordinaten passen nicht mehr
            self.statusBar().showMessage(tr("{n} spot(s) processed.{missing}").format(n=count, missing=miss_txt), 10000)
            return
        if left:
            self.canvas.add_effects([rect for _label, rect in left], "redact")
            self.statusBar().showMessage(
                tr("{n} spot(s) processed – {left} were still readable and were additionally redacted.{missing} Undo with Ctrl+Z.").format(n=count, left=len(left), missing=miss_txt), 12000)
        else:
            self.statusBar().showMessage(
                tr("{n} spot(s) processed, checked: nothing readable anymore.{missing} Undo with Ctrl+Z.").format(n=count, missing=miss_txt), 10000)

    # --- Ideen-Sammlung -----------------------------------------------------------
    def save_idea(self) -> None:
        store = self.ctx.store
        existing = store.get(self.idea_id) if self.idea_id else None
        clip = QGuiApplication.clipboard().text().strip()
        hint = clip if clip.startswith(("http://", "https://")) and "\n" not in clip else ""
        img = self.current_image()
        dlg = IdeaDialog(img, self, idea=existing, source_hint=hint,
                         known_tags=[t for t, _ in store.tag_counts()])
        if dlg.exec() != IdeaDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if existing is not None and dlg.replace_existing():
            store.update(existing.id, **values)
            store.replace_image(existing.id, img)
            new_id = existing.id
        else:
            new_id = store.add(img, **values)
            self.idea_id = new_id
        ideas.start_ocr_index(store, new_id, self.ctx.cfg.ocr_langs)
        self._dirty = False
        self.statusBar().showMessage(tr("Saved in the ideas collection (ksnapmark --ideas opens it)."), 8000)

    # --- Schließen --------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        if self._dirty and self.canvas.can_undo():
            answer = QMessageBox.question(
                self, tr("Discard?"), tr("The changes were neither copied nor saved. Discard?"),
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        event.accept()
