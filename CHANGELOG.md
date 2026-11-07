# Changelog

## 0.9.1
- A new screenshot is copied to the clipboard as soon as the editor opens, so it can be pasted without clicking *Copy*. After editing, *Copy* (or `Enter`) updates the clipboard; the status bar reminds you. Setting `auto_copy` / Settings checkbox turns it off. History entries, ideas and opened files are not copied.

## 0.9.0
- **Searchable history**: tray menu → History → *Search history …* (or `ksnapmark --history`): thumbnails, live filter over the text found in your screenshots (Tesseract, indexed in the background, local `index.json`; `history_ocr = false` turns it off).
- **More upload targets**: Share → Upload offers 0x0.st (or a compatible server), catbox.moe and uguu.se.
- **Spotlight tool (S)** dims everything outside the drawn box.
- **Frame and shadow** dialog: gradient/flat background, padding, rounded corners, soft shadow.

## 0.8.1
- Scrolling capture: fixed footers (status bars, panels at the bottom of the region) are no longer repeated at every seam; they appear once at the end.

## 0.8.0
- **Scrolling capture** (`ksnapmark --scroll`, tray menu *Scrolling capture*): select a region, scroll the content yourself, KSnapMark takes frames and stitches them into one tall image (works with fixed headers; finish with the *Finish* button). Opens in the editor.

## 0.7.1
- The magnifier with color value during region selection is now off by default; `L` toggles it, setting `show_loupe` / Settings checkbox keeps it on. `C` still copies the color.

## 0.7.0
- **Select tool (V)**: annotations stay editable – click, move, resize via handles, recolor, change width/fill, nudge with arrow keys, delete with `Del`, double-click to edit text. Effects (blur, pixelate, redact) can be moved and restore the pixels beneath. Numbering is renumbered after deleting.
- New setting `include_cursor` (Settings → *Include the mouse pointer*): captures the mouse pointer with KWin, spectacle, grim, gnome-screenshot and scrot (not with the desktop portal).

## 0.6.1
- Application icon as an SVG (the familiar blue frame with corner marks), used for the tray, windows, launcher entries and autostart.
- Hardening: private temp file for sharing, `usedforsecurity=False` for the history hash, unused imports removed.
- Packaging: icon installed into the hicolor theme (launcher entries use `Icon=ksnapmark`).

## 0.6.0
- User interface in **English and German**, following the system language; new setting *Language* (auto / English / Deutsch).
- Diagnostic output (`--doctor`, `--selftest`) and technical error messages are now English.
- Translation catalog in `ksnapmark/translations/`, with a test that keeps it complete.

## 0.5.0
- Renamed from SnapMark to **KSnapMark** (command `ksnapmark`); settings, history and ideas are migrated automatically.
- MIT license, English README (German version kept as `README.de.md`), SECURITY and CONTRIBUTING notes.
- Test suite in `tests/` (`python tests/run_all.py`) and a GitHub Actions workflow.

## 0.4.2
- X11-only capture tools (maim, scrot, import) are skipped on Wayland.

## 0.4.0 – 0.4.1
- Settings dialog, history in the tray menu, magnifier and color picker, QR/barcode reading, pin to screen,
  window snapping (KDE), screen recording and GIF conversion, `--selftest`, PKGBUILD.

## 0.3.x
- Resident background process with tray icon, built-in KWin/portal capture, auto-redact with blur,
  optional persistent term list.

## 0.1 – 0.2
- Region capture, editor, OCR, ideas collection.
