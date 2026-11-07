import os, stat, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from ksnapmark.style import STYLE
app = QApplication(["t"]); app.setStyleSheet(STYLE)
from ksnapmark.app import Context
import ksnapmark.editor as ed
from ksnapmark import findtext, dialogs
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
SCR = os.path.dirname(os.path.abspath(__file__))

img = QImage(900, 200, QImage.Format.Format_RGB32); img.fill(QColor("white"))
p = QPainter(img); f = QFont("DejaVu Sans"); f.setPixelSize(26); p.setFont(f); p.setPen(QColor("black"))
p.drawText(20, 50, "Rechnung für Max Mustermann"); p.drawText(20, 110, "Firma: Systemtechnik GmbH"); p.drawText(20, 170, "Bestellung 4711"); p.end()

check("Liste anfangs leer, keine Datei", findtext.load_saved() == "" and not findtext.saved_path().exists())
d = dialogs.AutoRedactDialog(None, "", "blur", True, True, "", False)
d.show(); app.processEvents()
check("Standard: Liste aus und ausgeblendet", not d.use_saved.isChecked() and not d.saved.isVisible())
d.use_saved.setChecked(True); app.processEvents()
check("Haken blendet Eingabe ein", d.saved.isVisible())
d.saved.setPlainText("Systemtechnik"); d.terms.setPlainText("Mustermann")
v = d.values()
check("Begriffe = Sitzung + dauerhaft", v["terms"] == ["Mustermann", "Systemtechnik"], str(v["terms"]))
d.grab().save(f"{SCR}/autoredact_dialog2.png"); d.close()
d2 = dialogs.AutoRedactDialog(None, "Mustermann", "blur", True, True, "Systemtechnik", False)
check("Liste aus -> nur Sitzungsbegriffe", d2.values()["terms"] == ["Mustermann"])

def fake_exec(self):
    self.use_saved.setChecked(True); self.saved.setPlainText("Systemtechnik"); self.terms.setPlainText("")
    self.patterns.setChecked(False); return self.DialogCode.Accepted
ed.AutoRedactDialog.exec = fake_exec
win = ed.EditorWindow(img, 1.0, Context()); win.show()
win.auto_redact()
end = time.monotonic() + 60
while time.monotonic() < end and not win.canvas.items:
    app.processEvents(); time.sleep(0.05)
check("Dauerhafter Begriff wird gefunden und bearbeitet", len(win.canvas.items) == 1, str(len(win.canvas.items)))
path = findtext.saved_path()
check("Datei gespeichert, nur fuer Benutzer (0600)", path.exists() and stat.S_IMODE(path.stat().st_mode) == 0o600, oct(stat.S_IMODE(path.stat().st_mode)) if path.exists() else "fehlt")
check("Neu laden liefert Inhalt", findtext.load_saved().strip() == "Systemtechnik")
check("Leeren loescht die Datei", findtext.save_saved("  ") and not path.exists())
end = time.monotonic() + 30
while time.monotonic() < end and "geprüft" not in win.statusBar().currentMessage() and "zusätzlich" not in win.statusBar().currentMessage():
    app.processEvents(); time.sleep(0.05)
win._dirty = False
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
