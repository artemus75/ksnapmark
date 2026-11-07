import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
from ksnapmark.style import STYLE
app = QApplication(["t"]); app.setStyleSheet(STYLE)
from ksnapmark import config, system
from ksnapmark.app import Context, Controller
from ksnapmark.settings_ui import SettingsDialog
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
SCR = os.path.dirname(os.path.abspath(__file__))
for cls in (QMessageBox,):
    cls.warning = staticmethod(lambda *a, **k: warned.append(a[2] if len(a) > 2 else "")); cls.information = staticmethod(lambda *a, **k: infos.append(a[2] if len(a) > 2 else ""))
warned, infos = [], []

cfgfile = config.CONFIG_DIR / "config.toml"
config.CONFIG_DIR.mkdir(parents=True)
cfgfile.write_text('save_dir = "~/Bilder"\nmein_eigener_schluessel = "bleibt"\nupload_expires_hours = 48\n')
cfg = config.load()
check("bestehende Datei gelesen", cfg.upload_expires_hours == 48 and str(cfg.save_dir).endswith("Bilder"))
ctx = Context(); d = SettingsDialog(ctx.cfg, ctx.history); d.show(); app.processEvents(); d.grab().save(f"{SCR}/settings.png")
check("Dialog zeigt aktuelle Werte", d.upload_hours.value() == 48 and d.save_dir.text().endswith("Bilder"))
d.ocr_langs.setText('deu"+eng'); d.history_size.setValue(5); d.upload_hours.setValue(12)
d.backend.setCurrentIndex(d.backend.findData("portal")); d.autostart.setChecked(True)
d._save(); app.processEvents()
new = config.load()
check("Werte gespeichert und neu geladen", new.upload_expires_hours == 12 and new.history_size == 5 and new.capture_backend == "portal" and new.ocr_langs == 'deu"+eng', str(new))
check("Sonderzeichen sauber maskiert", 'deu"+eng' == new.ocr_langs)
txt = cfgfile.read_text()
check("unbekannter Schluessel bleibt", 'mein_eigener_schluessel = "bleibt"' in txt)
check("Home als ~ gespeichert", 'save_dir = "~/Bilder"' in txt, txt.splitlines()[1])
check("laufende Instanz sofort aktualisiert", ctx.cfg.history_size == 5 and ctx.cfg.capture_backend == "portal")
check("Autostart per Dialog gesetzt", system.autostart_enabled())
check("Hintergrundbetrieb unveraendert -> kein Neustart-Hinweis", infos == [])
d2 = SettingsDialog(ctx.cfg, ctx.history); d2.upload_url.setText("http://unsicher.example"); d2._save()
check("http-Upload wird abgelehnt", warned and "https" in warned[-1] and config.load().upload_url == "https://0x0.st", str(warned))
d3 = SettingsDialog(ctx.cfg, ctx.history); d3.resident.setChecked(False); d3.autostart.setChecked(False); d3._save()
check("Neustart-Hinweis bei Hintergrundbetrieb", infos and "Neustart" in infos[-1])
check("Autostart per Dialog entfernt", not system.autostart_enabled())
# Controller
ctl = Controller(app, ctx, True); ctl.setup_tray()
ctl.open_settings(); first = ctl._settings_win; ctl.open_settings()
check("Einstellungsfenster nur einmal", ctl._settings_win is first and first.isVisible())
ctx.cfg.history = False; ctl.apply_config()
check("Verlaufsmenue wird ausgeblendet", not ctl._history_menu.menuAction().isVisible())
ctx.cfg.history = True; ctl.apply_config()
check("... und wieder eingeblendet", ctl._history_menu.menuAction().isVisible())
check("Tray-Eintrag Einstellungen", any(a.text().startswith("Einstellungen") for a in ctl.menu.actions()))
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
