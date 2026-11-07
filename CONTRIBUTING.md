# Contributing

Bug reports and pull requests are welcome.

- Run `python tests/run_all.py` before opening a pull request (needs PySide6, pillow, qrcode, dbus-next, opencv;
  OCR tests need `tesseract`, QR tests `zbar`).
- When reporting a problem on a specific desktop, attach the output of `ksnapmark --selftest`.
- **Translations:** source strings in the code are English and wrapped in `tr("…")` (`ksnapmark/i18n.py`). A language is
  a dict in `ksnapmark/translations/<code>.py` (`CATALOG = {"English text": "translation"}`, see `de.py`). To add one:
  copy `de.py`, translate the values, add the code to `SUPPORTED` in `i18n.py`, and run `python tests/i18n_test.py`
  (it checks that every `tr()` text has an entry and that `{placeholders}` match). Use `{name}` placeholders with
  `.format(...)`, never f-strings, inside `tr()`.
- Please keep new features optional where they touch privacy (uploads, stored data).
