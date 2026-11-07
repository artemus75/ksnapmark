import os, subprocess, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
SCR = os.path.dirname(os.path.abspath(__file__))
os.environ["WAYLAND_DISPLAY"] = "wayland-test"
mock = subprocess.Popen([sys.executable, f"{SCR}/mock_scripting.py"], stdout=subprocess.PIPE, text=True)
assert mock.stdout.readline().strip() == "READY"
from PySide6.QtWidgets import QApplication
app = QApplication(["t"])
from ksnapmark import windows
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
check("Scripting-Dienst erkannt", windows.available())
t = time.monotonic(); wins = windows.query_windows(); dt = time.monotonic() - t
check("Fensterliste empfangen", wins is not None, str(wins)[:80])
names = [w.title for w in wins or []]
check("nur echte Fenster (unten -> oben)", names == ["Browser", "Dialog", "Auf allen"], str(names))
check("Geometrie gerundet", wins and wins[-1].rect.getRect() == (1400, 61, 900, 700), str(wins[-1].rect.getRect()) if wins else "")
check("aktives Fenster erkannt", wins and wins[-1].active and not wins[0].active)
check("App-Name/pid", wins and wins[0].app == "firefox" and wins[0].pid == 11)
check("schnell genug", dt < 5.0, f"{dt*1000:.0f} ms")
# zweiter Aufruf (Dienst bleibt registriert, Skript wird jeweils neu geladen)
w2 = windows.query_windows()
check("zweiter Aufruf funktioniert", w2 is not None and len(w2) == 3)
# Skriptdateien aufgeraeumt
rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
left = [f for f in os.listdir(rt) if f.startswith("ksnapmark-windows-")]
check("temporaere Skriptdateien geloescht", not left, str(left))
# Fehlerfaelle
check("kaputtes JSON -> leere Liste", windows.parse_windows("{{") == [] and windows.parse_windows('{"x":1}') == [])
check("winzige/kaputte Eintraege ignoriert", [w.title for w in windows.parse_windows('{"windows":[{"title":"a","x":0,"y":0,"w":5,"h":5},{"title":"b"},{"title":"ok","x":1,"y":2,"w":300,"h":200}]}')] == ["ok"])
mock.terminate(); mock.wait()
# ohne KWin
del os.environ["WAYLAND_DISPLAY"]
check("ohne Wayland/KWin: None", windows.query_windows() is None)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
