import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication
app = QApplication(["t"])
from ksnapmark import capture

class FakeScreen:
    def __init__(self, name, geo, virt, dpr): self.n, self._g, self._v, self._d = name, geo, virt, dpr
    def name(self): return self.n
    def geometry(self): return self._g
    def virtualGeometry(self): return self._v
    def devicePixelRatio(self): return self._d

virt = QRect(0, 0, 10453, 1600)
S = [FakeScreen("eDP-1", QRect(0, 0, 2133, 1333), virt, 2.0),
     FakeScreen("DP-9", QRect(2133, 0, 1920, 1200), virt, 1.0),
     FakeScreen("DP-10", QRect(4053, 0, 2560, 1440), virt, 1.0),
     FakeScreen("DP-4", QRect(6613, 0, 3840, 1600), virt, 1.0)]
QGuiApplication.screens = staticmethod(lambda: S)
cols = ["#ff0000", "#00ff00", "#0000ff", "#ffff00"]

# Gesamtbild bei Skalierung 2 (wie Spectacle/KWin es liefert), Groesse > 256 MB
full = QImage(10453 * 2, 3200, QImage.Format.Format_RGB32)
full.fill(QColor("#202020"))
p = QPainter(full)
for s, c in zip(S, cols):
    g = s.geometry(); p.fillRect(g.x() * 2, g.y() * 2, g.width() * 2, g.height() * 2, QColor(c))
p.end()
print("Gesamtbild:", full.width(), "x", full.height(), f"= {full.width()*full.height()*4/1e6:.0f} MB")
ok = True
for s, c in zip(S, cols):
    im = capture._crop_to_screen(full, s)
    exp_w = round(s.geometry().width() * s.devicePixelRatio())
    good = (im.width() == exp_w and im.pixelColor(5, 5) == QColor(c) and im.pixelColor(im.width() - 5, im.height() - 5) == QColor(c)
            and abs(im.devicePixelRatio() - s.devicePixelRatio()) < 0.01)
    ok &= good
    print("PASS" if good else "FAIL", s.name(), im.width(), "x", im.height(), "dpr", round(im.devicePixelRatio(), 3))
print("Plausibel (Gesamtbild):", capture._covers_all_screens(full))
single = QImage(3840, 1600, QImage.Format.Format_RGB32); single.fill(QColor("#123456"))
print("Einzelmonitor-Bild wird abgelehnt:", not capture._covers_all_screens(single))

# Grosses PNG von Datei laden (Limit angehoben) inkl. verzoegert geschriebener Datei
d = tempfile.mkdtemp(); path = os.path.join(d, "big.png")
fake = os.path.join(d, "spectacle")
open(fake, "w").write(f"#!/usr/bin/env bash\n( sleep 1; cp {d}/src.png \"${{@: -1}}\" ) >/dev/null 2>&1 &\nexit 0\n")
os.chmod(fake, 0o755)
full.save(os.path.join(d, "src.png"), "PNG")
os.environ["PATH"] = d + ":" + os.environ["PATH"]
os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
img = capture._spectacle()
print("Grosses PNG geladen:", img is not None and img.width() == 20906, capture.LAST_ERRORS[:2])
sys.exit(0 if ok and img is not None else 1)
