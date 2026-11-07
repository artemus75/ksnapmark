import os, sys, time, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from ksnapmark.style import STYLE
app = QApplication(["t"]); app.setStyleSheet(STYLE)
from ksnapmark.app import Context
from ksnapmark.editor import EditorWindow
from ksnapmark import dialogs
SCR = os.path.dirname(os.path.abspath(__file__))

img = QImage(900, 260, QImage.Format.Format_RGB32); img.fill(QColor("white"))
p = QPainter(img); f = QFont("DejaVu Sans"); f.setPixelSize(26); p.setFont(f); p.setPen(QColor("black"))
p.drawText(20, 50, "Rechnung für Max Mustermann"); p.drawText(20, 100, "Kontakt: m.mustermann@example.com")
p.drawText(20, 150, "Firma: Müller Systemtechnik GmbH"); p.drawText(20, 200, "Bestellung 4711 vom 05.11.2026"); p.end()

ctx = Context(); win = EditorWindow(img, 1.0, ctx); win.show()
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))

# Dialog-Screenshot
d = dialogs.AutoRedactDialog(win, "Max Mustermann\nMueller")
d.show(); app.processEvents(); d.grab().save(f"{SCR}/autoredact_dialog.png"); d.close()

# Dialog automatisch bestätigen
orig_exec = dialogs.AutoRedactDialog.exec
def fake_exec(self):
    self.terms.setPlainText("Max Mustermann\nMueller\nGibtsNicht Xyz")
    self.kind.setCurrentIndex(0); self.patterns.setChecked(True)
    return self.DialogCode.Accepted
dialogs.AutoRedactDialog.exec = fake_exec
import ksnapmark.editor as ed; ed.AutoRedactDialog.exec = fake_exec
n_before = len(win.canvas.items)
win.auto_redact()
end = time.monotonic() + 60
while time.monotonic() < end and len(win.canvas.items) == n_before:
    app.processEvents(); time.sleep(0.05)
check("Effekte angelegt", len(win.canvas.items) > n_before, f"{len(win.canvas.items)} Items")
kinds = {it.kind for it in win.canvas.items}
check("Effekt = Blur", kinds == {"blur"}, str(kinds))
msg = win.statusBar().currentMessage(); print("Status:", msg)
check("meldet nicht gefundenen Begriff", "GibtsNicht Xyz" in msg)
# Nachprüfung abwarten
end = time.monotonic() + 60
while time.monotonic() < end and "geprüft" not in win.statusBar().currentMessage() and "zusätzlich" not in win.statusBar().currentMessage():
    app.processEvents(); time.sleep(0.05)
msg = win.statusBar().currentMessage(); print("Status:", msg)
check("Nachprüfung meldet Ergebnis", "geprüft" in msg or "zusätzlich" in msg)
from ksnapmark import ocr, findtext
left = findtext.find_terms(ocr.ocr_words(win.canvas.result_image(), "deu+eng"), ["Max Mustermann", "Mueller"])
check("Ergebnisbild: Namen nicht mehr lesbar", not left, str(len(left)))
win.canvas.result_image().save(f"{SCR}/autoredact_result.png")
check("Begriffe fuer die Sitzung gemerkt", "Max Mustermann" in ctx.last_terms)
win._dirty = False
sys.exit(0 if all(res) else 1)
