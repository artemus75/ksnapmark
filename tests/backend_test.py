import os, subprocess, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
SCR = os.path.dirname(os.path.abspath(__file__))
os.environ["WAYLAND_DISPLAY"] = "wayland-test"
os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
os.environ["PATH"] = "/nonexistent"  # weder spectacle noch grim

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtWidgets import QApplication
app = QApplication(["t"])
from ksnapmark import capture

res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))

class FS:
    def __init__(self, name, geo, virt): self._n, self._g, self._v = name, geo, virt
    def name(self): return self._n
    def geometry(self): return self._g
    def virtualGeometry(self): return self._v
    def devicePixelRatio(self): return 1.0

def run(env_extra):
    env = dict(os.environ, **env_extra)
    mock = subprocess.Popen([sys.executable, f"{SCR}/mock_services.py"], stdout=subprocess.PIPE, text=True,
                            env={**env, "PATH": "/usr/bin:/bin:/usr/local/bin"})
    assert mock.stdout.readline().strip() == "READY"
    return mock

# 1) KWin erlaubt: zwei Monitore einzeln aufgenommen
mock = run({})
virt = QRect(0, 0, 1200, 400)
a, b = FS("DP-4", QRect(0, 0, 400, 200), virt), FS("eDP-1", QRect(400, 0, 800, 400), virt)
shots = capture.capture_screens([a, b])
check("Backend kwin gewaehlt", capture.LAST_BACKEND == "kwin", capture.LAST_BACKEND + str(capture.LAST_ERRORS))
check("kwin: zwei Bilder", len(shots) == 2)
if len(shots) == 2:
    check("kwin: DP-4 rot, eDP-1 gruen", shots[0][1].pixelColor(5, 5) == QColor(255, 0, 0)
          and shots[1][1].pixelColor(5, 5) == QColor(0, 255, 0))
    check("kwin: dpr", abs(shots[0][1].devicePixelRatio() - 1.0) < 1e-6)
mock.terminate(); mock.wait()

# 2) KWin verweigert -> Portal als Rueckfall (Portalbild 640x360 passt zum Fake-Desktop)
mock = run({"MOCK_KWIN_DENY": "1"})
virt = QRect(0, 0, 640, 360)
c = FS("DP-4", QRect(0, 0, 640, 360), virt)
QGuiApplication.screens = staticmethod(lambda: [c])
shots = capture.capture_screens([c])
check("Rueckfall auf Portal", capture.LAST_BACKEND == "portal" and len(shots) == 1,
      capture.LAST_BACKEND + " | " + "; ".join(capture.LAST_ERRORS))
check("Fehler von KWin wurde notiert", any("NoAuthorized" in e for e in capture.LAST_ERRORS))
mock.terminate(); mock.wait()

# 3) alles verweigert -> leer + Fehlermeldung
mock = run({"MOCK_KWIN_DENY": "1", "MOCK_PORTAL_DENY": "1"})
shots = capture.capture_screens([c])
check("alles verweigert -> leer", shots == [])
msg = capture.failure_message()
check("Fehlermeldung nennt Gruende", "NoAuthorized" in msg and "denied" in msg, msg[:120])
mock.terminate(); mock.wait()

# 4) Reihenfolge / bevorzugtes Verfahren
check("Reihenfolge KDE", capture.backend_order()[:2] == ["kwin", "spectacle"])
check("bevorzugtes Verfahren", capture.backend_order("portal")[0] == "portal")
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
