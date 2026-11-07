import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
app = QApplication(["t"])
from ksnapmark.pin import PinWindow
from ksnapmark import system
from ksnapmark.app import Context, Controller
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
img = QImage(400, 200, QImage.Format.Format_RGB32); img.fill(QColor("#336699"))
p = QPainter(img); p.fillRect(0, 0, 100, 100, QColor("#ff8800")); p.end()
w = PinWindow(img, 2.0); w.show(); app.processEvents()
check("Groesse = Pixel / dpr", (w.width(), w.height()) == (200, 100), f"{w.width()}x{w.height()}")
def wheel(delta, mods=Qt.KeyboardModifier.NoModifier):
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, delta), Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(w, ev)
wheel(120); check("Mausrad vergroessert (Seitenverhaeltnis bleibt)", w.width() > 200 and abs(w.height() / w.width() - 0.5) < 0.02, f"{w.width()}x{w.height()}")
wheel(-120); wheel(-120); check("Mausrad verkleinert", w.width() < 200)
wheel(-120, Qt.KeyboardModifier.ControlModifier); check("Strg+Rad: Transparenz sinkt", w._opacity < 1.0, f"{w._opacity:.1f}")
for _ in range(20): wheel(-120, Qt.KeyboardModifier.ControlModifier)
check("Transparenz hat Untergrenze", w._opacity >= 0.2)
w.set_opacity(1.0)
w.resize(500, 250); w.grab().save(f"{SCR}/pin.png") if (SCR := os.path.dirname(os.path.abspath(__file__))) else None
copied = []
import ksnapmark.editor as ed
orig = ed.png_bytes
system.clipboard_set = lambda data, mime: copied.append((len(data), mime)) or True; system.notify = lambda *a, **k: None
QTest.keyClick(w, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
check("Strg+C kopiert PNG", copied and copied[0][1] == "image/png", str(copied))
emitted = []; w.open_in_editor.connect(lambda i: emitted.append(i.size()))
w.open_in_editor.emit(QImage(w._image)); check("Signal Im Editor oeffnen", emitted and emitted[0].width() == 400)
closed = []
QTest.keyClick(w, Qt.Key.Key_Escape); app.processEvents()
check("Esc schliesst", not w.isVisible())
w2 = PinWindow(img, 1.0); w2.show(); QTest.mouseDClick(w2, Qt.MouseButton.LeftButton, pos=QPoint(20, 20)); app.processEvents()
check("Doppelklick schliesst", not w2.isVisible())
big = QImage(6000, 4000, QImage.Format.Format_RGB32); big.fill(QColor("white"))
w3 = PinWindow(big, 1.0); av = QApplication.primaryScreen().availableGeometry()
check("Riesiges Bild passt auf den Monitor", w3.width() <= av.width() and w3.height() <= av.height(), f"{w3.width()}x{w3.height()} in {av.width()}x{av.height()}")
# Controller: pin_image wird gehalten und beim Schliessen freigegeben
ctx = Context(); ctl = Controller(app, ctx, True)
pw = ctl.pin_image(img, 1.0)
check("Controller haelt das Fenster", pw in ctx.windows)
pw.close(); app.processEvents(); app.processEvents()
import shiboken6
check("nach Schliessen freigegeben", all(shiboken6.isValid(x) for x in ctx.windows) and pw not in [x for x in ctx.windows if shiboken6.isValid(x)])
# Direktmodus
from ksnapmark.ipc import Job
n0 = len(ctx.windows)
ctl.run_direct(Job(mode="pin"), img, 1.0)
check("Direktmodus pin oeffnet Fenster und beendet nicht", len(ctx.windows) == n0 + 1)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
