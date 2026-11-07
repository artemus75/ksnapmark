import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(["t"])
from ksnapmark.app import Controller, Context
c = Controller(app, Context(), True)
got = []
c.handle = lambda j: got.append(j)
c.setup_tray()
acts = [a for a in c.menu.actions()]
print([a.text() or "---" for a in acts])
res = []
def check(n, ok, extra=""): res.append(ok); print(("PASS " if ok else "FAIL ") + n)
check("Tray angelegt", c.tray is not None and c.tray.isVisible() or c.tray is not None)
texts = [a.text() for a in acts if not a.isSeparator()]
check("Menü enthält alle Einträge", all(any(t.startswith(x) for t in texts) for x in ("Bereich aufnehmen", "Ganzen Bildschirm", "Text aus Bereich", "QR-Code", "Bereich anheften", "Bildschirmaufnahme", "Ideen-Sammlung", "Verlauf", "Einstellungen", "Beim Anmelden", "KSnapMark beenden")), str(texts))
by = {a.text(): a for a in acts if not a.isSeparator()}
for t in ("Bereich aufnehmen", "Ganzen Bildschirm aufnehmen", "Text aus Bereich kopieren (OCR)", "Ideen-Sammlung öffnen", "QR-Code aus Bereich lesen", "Bereich anheften (schwebend)", "Einstellungen …"): by[t].trigger()
check("Aufträge korrekt", [(j.action, j.mode, j.full) for j in got] ==
      [("capture","edit",False),("capture","edit",True),("capture","ocr",False),("ideas","edit",False),("capture","qr",False),("capture","pin",False),("settings","edit",False)])
auto = [a for a in acts if a.isCheckable()][0]
auto.setChecked(True)
from ksnapmark import system
check("Autostart per Menü an", system.autostart_enabled())
auto.setChecked(False)
check("Autostart per Menü aus", not system.autostart_enabled())
sys.exit(0 if all(res) else 1)
