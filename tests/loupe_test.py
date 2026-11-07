import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtCore import QPoint, Qt, QPointF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
app = QApplication(["t"])
from ksnapmark.overlay import SelectionOverlay
from ksnapmark import system
SCR = os.path.dirname(os.path.abspath(__file__))
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
screen = QGuiApplication.primaryScreen(); g = screen.geometry()
shot = QImage(g.width(), g.height(), QImage.Format.Format_RGB32); shot.fill(QColor("#336699"))
p = QPainter(shot); p.fillRect(100, 100, 60, 60, QColor("#ff8800")); p.fillRect(130, 130, 10, 10, QColor("#00cc44")); p.end()
ov = SelectionOverlay(screen, shot); ov.resize(g.width(), g.height()); ov.show()
check("Lupe standardmaessig aus", ov.show_loupe is False)
ov.show_loupe = True
QTest.keyClick(ov, Qt.Key.Key_L); check("L schaltet Lupe aus", ov.show_loupe is False); QTest.keyClick(ov, Qt.Key.Key_L); check("L schaltet Lupe ein", ov.show_loupe is True)
ov._cur = QPoint(135, 135)
check("Farbe unter Zeiger", ov.color_under_cursor().name() == "#00cc44", ov.color_under_cursor().name())
ov._cur = QPoint(110, 110)
check("Farbe unter Zeiger (Orange)", ov.color_under_cursor().name() == "#ff8800")
ov._cur = QPoint(0, 0); ov.update(); app.processEvents()
ov.grab()  # Rand: darf nicht abstuerzen
ov._cur = QPoint(g.width() - 1, g.height() - 1); ov.grab()
check("Lupe am Rand ohne Absturz", True)
ov._cur = QPoint(132, 132); ov.update(); app.processEvents(); ov.grab().save(f"{SCR}/loupe.png")
copied = []
system.clipboard_set_text = lambda t: copied.append(t) or True; system.notify = lambda *a, **k: None
QTest.keyClick(ov, Qt.Key.Key_C)
check("Taste C kopiert Hex", copied == ["#00CC44"], str(copied))
check("Overlay bleibt offen nach C", ov.isVisible())

# Pipette im Editor
from ksnapmark.app import Context
import ksnapmark.editor as ed
w = ed.EditorWindow(shot.copy(), 1.0, Context(), record=False); w.show(); app.processEvents()
w.set_tool("pick")
c = w.canvas; vs = c.view_scale
pos = QPointF(135 * vs, 135 * vs)
QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=pos.toPoint())
check("Pipette uebernimmt Zeichenfarbe", c.color.lower() == "#00cc44", c.color)
check("Pipette kopiert Hex", copied[-1] == "#00CC44", str(copied))
check("Pipette zeichnet nichts", len(c.items) == 0)
w._dirty = False
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
