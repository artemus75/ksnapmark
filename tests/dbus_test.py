import os
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
SCR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))

mock = subprocess.Popen([sys.executable, f"{SCR}/mock_services.py"], stdout=subprocess.PIPE, text=True)
assert mock.stdout.readline().strip() == "READY"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
app = QApplication(["t"])
from ksnapmark import dbus_capture as dc

res = []
def check(name, cond, extra=""):
    res.append(cond); print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))

os.environ["WAYLAND_DISPLAY"] = "wayland-test"
check("kwin_available erkennt Dienst", dc.kwin_available())
check("portal_available erkennt Dienst", dc.portal_available())

try:
    img = dc.kwin_capture_screen("DP-4")
    check("KWin: Monitor DP-4 (400x200, rot)", (img.width(), img.height()) == (400, 200) and img.pixelColor(10, 10) == QColor(255, 0, 0), f"{img.width()}x{img.height()} {img.pixelColor(10,10).name()}")
    img = dc.kwin_capture_screen("eDP-1")
    check("KWin: Monitor eDP-1 (800x400, gruen)", (img.width(), img.height()) == (800, 400) and img.pixelColor(799, 399) == QColor(0, 255, 0))
except Exception as exc:
    check("KWin-Aufnahme", False, repr(exc))

try:
    img = dc.portal_screenshot(timeout_s=10)
    check("Portal: Bild 640x360 empfangen", (img.width(), img.height()) == (640, 360) and img.pixelColor(5, 5) == QColor("#336699"))
except Exception as exc:
    check("Portal-Aufnahme", False, repr(exc))

mock.terminate(); mock.wait()
# zweiter Lauf: Zugriff verweigert
env = dict(os.environ, MOCK_KWIN_DENY="1", MOCK_PORTAL_DENY="1")
mock = subprocess.Popen([sys.executable, f"{SCR}/mock_services.py"], stdout=subprocess.PIPE, text=True, env=env)
assert mock.stdout.readline().strip() == "READY"
try:
    dc.kwin_capture_screen("DP-4"); check("KWin verweigert -> Fehler", False)
except dc.CaptureError as exc:
    check("KWin verweigert -> CaptureError mit Meldung", "NoAuthorized" in str(exc), str(exc))
try:
    dc.portal_screenshot(timeout_s=10); check("Portal verweigert -> Fehler", False)
except dc.CaptureError as exc:
    check("Portal verweigert -> CaptureError", "denied" in str(exc), str(exc))
mock.terminate()
print("ERGEBNIS:", sum(res), "von", len(res))
sys.exit(0 if all(res) else 1)
