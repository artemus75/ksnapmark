import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
app = QApplication(["t"])
from ksnapmark.overlay import SelectionOverlay
from ksnapmark.windows import Win
SCR = os.path.dirname(os.path.abspath(__file__))
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
screen = QGuiApplication.primaryScreen(); g = screen.geometry()
shot = QImage(g.width(), g.height(), QImage.Format.Format_RGB32); shot.fill(QColor("#223344"))
p = QPainter(shot); p.fillRect(100, 100, 300, 200, QColor("#ffffff")); p.fillRect(250, 150, 300, 250, QColor("#ffcc66")); p.end()
wins = [Win("Browser", "firefox", QRect(100, 100, 300, 200)), Win("Terminal", "konsole", QRect(250, 150, 300, 250)),
        Win("Anderer Monitor", "x", QRect(g.x() + g.width() + 50, 0, 400, 300))]
ov = SelectionOverlay(screen, shot, wins); ov.resize(g.width(), g.height()); ov.show(); app.processEvents()
got = []; ov.selected.connect(lambda img, r: got.append((img.width(), img.height())))
check("nur Fenster dieses Monitors", len(ov._wins) == 2, str(len(ov._wins)))
QTest.mouseMove(ov, QPoint(300, 200)); app.processEvents()
check("Hover: oberstes Fenster (Terminal) gewinnt in der Ueberlappung", ov._hover_title == "Terminal", ov._hover_title)
QTest.mouseMove(ov, QPoint(120, 120)); app.processEvents()
check("Hover: Browser ausserhalb der Ueberlappung", ov._hover_title == "Browser")
ov.grab().save(f"{SCR}/snap.png")
QTest.mouseMove(ov, QPoint(700, 700)); app.processEvents()
check("Hover: nichts ausserhalb", ov._hover is None)
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(700, 700)); app.processEvents()
check("Klick ins Leere waehlt nichts", got == [])
QTest.mouseMove(ov, QPoint(120, 120)); QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(120, 120)); app.processEvents()
check("Klick waehlt Fenster (300x200)", got == [(300, 200)], str(got))
got.clear()
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(110, 110)); QTest.mouseMove(ov, QPoint(180, 160)); QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(180, 160)); app.processEvents()
check("Ziehen ueberschreibt Einrasten (71x51, Endpunkte inklusive)", got == [(71, 51)], str(got))
ov2 = SelectionOverlay(screen, shot); ov2.resize(g.width(), g.height()); ov2.show()
got2 = []; ov2.selected.connect(lambda i, r: got2.append(1))
QTest.mouseClick(ov2, Qt.MouseButton.LeftButton, pos=QPoint(120, 120)); app.processEvents()
check("ohne Fensterliste: Klick tut nichts (wie bisher)", got2 == [] and not ov2._wins)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
