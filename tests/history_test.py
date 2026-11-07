import os, stat, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(["t"])
from ksnapmark.app import Controller, Context
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
def img(c, w=300, h=200):
    i = QImage(w, h, QImage.Format.Format_RGB32); i.fill(QColor(c)); return i

ctx = Context(); ctx.cfg.history_size = 3
ctl = Controller(app, ctx, True); ctl.setup_tray()
h = ctx.history
check("Verlauf anfangs leer", h.entries() == [])
n1 = h.add(img("red")); time.sleep(0.01)
check("Eintrag angelegt", n1 and len(h.entries()) == 1)
check("Ordner 0700, Datei 0600", stat.S_IMODE(h.dir.stat().st_mode) == 0o700 and stat.S_IMODE((h.dir / n1).stat().st_mode) == 0o600)
n1b = h.add(img("red"), replace=n1)
check("unveraendertes Ersetzen: gleicher Eintrag", n1b == n1 and len(h.entries()) == 1)
n1c = h.add(img("blue"), replace=n1); time.sleep(0.01)
check("Ersetzen ersetzt statt zu duplizieren", n1c != n1 and len(h.entries()) == 1 and h.load(n1c).pixelColor(5, 5) == QColor("blue"))
for c in ("green", "yellow", "white"):
    h.add(img(c)); time.sleep(0.01)
check("Begrenzung auf 3", len(h.entries()) == 3, str(len(h.entries())))
check("neueste zuerst", h.load(h.entries()[0].name).pixelColor(5, 5) == QColor("white"))
check("Pfad-Trick wird abgelehnt", h.load("../../etc/passwd") is None)
ctl._history_menu.aboutToShow.emit() if False else ctl.fill_history_menu()
acts = [a for a in ctl._history_menu.actions() if not a.isSeparator()]
check("Menue: Suche + 3 Eintraege + Leeren", len(acts) == 5 and acts[0].text() == "Verlauf durchsuchen …", str([a.text() for a in acts]))
opened = []
ctl.open_editor = lambda image, dpr=1.0, idea_id=None, history_name=None, record=True: opened.append((history_name, record, image.width()))
acts[1].trigger()
check("Klick oeffnet Eintrag ohne neu aufzuzeichnen", opened and opened[0][1] is False and opened[0][2] == 300, str(opened))
acts[-1].trigger()
check("Verlauf leeren", h.entries() == [])
ctl.fill_history_menu()
check("leeres Menue zeigt Hinweis", [a.text() for a in ctl._history_menu.actions() if not a.isSeparator()][1] == "Noch keine Aufnahmen")

# Editor-Sitzung: Aufnahme + Kopieren ersetzt Eintrag
ctx2 = Context(); import ksnapmark.editor as ed
w = ed.EditorWindow(img("red", 400, 300), 1.0, ctx2); w.show()
e1 = ctx2.history.entries()
check("Editor legt Aufnahme im Verlauf ab", len(e1) == 1 and w.hist_name == e1[0].name)
w.canvas.add_effects([__import__("PySide6.QtCore", fromlist=["QRectF"]).QRectF(10, 10, 100, 100)], "redact")
w.copy_image()
e2 = ctx2.history.entries()
check("Kopieren ersetzt Eintrag durch bearbeitete Fassung", len(e2) == 1 and e2[0].name != e1[0].name and ctx2.history.load(e2[0].name).pixelColor(20, 20) == QColor("black"))
w._dirty = False; w.close()
w2 = ed.EditorWindow(img("red", 400, 300), 1.0, ctx2, record=False); w2.copy_image()
check("record=False: nichts aufgezeichnet", len(ctx2.history.entries()) == 1)
w2._dirty = False
ctx3 = Context(); ctx3.cfg.history = False
check("history=false: nichts gespeichert", ctx3.history.add(img("red")) is None)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
