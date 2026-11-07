"""New captures land in the clipboard right away; edits need a new Copy."""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["KSNAPMARK_LANG"] = "de"
home = tempfile.mkdtemp()
os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["t"])
from ksnapmark import config, system  # noqa: E402
from ksnapmark.app import Context  # noqa: E402
from ksnapmark.editor import EditorWindow  # noqa: E402
from ksnapmark.items import Item  # noqa: E402

res = []


def check(n, c, extra=""):
    res.append(bool(c)); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra and not c else ""))


sent = []
system.clipboard_set = lambda data, mime: sent.append((len(data), mime)) or True


def img():
    i = QImage(120, 80, QImage.Format.Format_ARGB32); i.fill(QColor("#336699")); return i


ctx = Context()
check("auto_copy is on by default", ctx.cfg.auto_copy is True)
ed = EditorWindow(img(), 1.0, ctx)
check("a new capture is copied immediately", len(sent) == 1 and sent[0][1] == "image/png", str(sent))
check("the status bar says so", "Zwischenablage" in ed.statusBar().currentMessage(), ed.statusBar().currentMessage())
ed.canvas.items.append(Item(kind="rect", p1=QPointF(5, 5), p2=QPointF(50, 40)))
ed.canvas._state_changed()
check("editing hints that Copy is needed", "Kopieren" in ed.statusBar().currentMessage(), ed.statusBar().currentMessage())
check("editing does not copy by itself", len(sent) == 1)
ed.copy_image()
check("Copy copies the edited version", len(sent) == 2)

n = len(sent)
EditorWindow(img(), 1.0, ctx, history_name="x.png", record=False)
EditorWindow(img(), 1.0, ctx, idea_id=3)
EditorWindow(img(), 1.0, ctx, record=False)
check("opening history/idea/files does not touch the clipboard", len(sent) == n)

ctx.cfg.auto_copy = False
EditorWindow(img(), 1.0, ctx)
check("setting off: nothing copied", len(sent) == n)

# fallback without wl-clipboard: Qt clipboard gets the image
ctx.cfg.auto_copy = True
system.clipboard_set = lambda data, mime: False
kept = []
system.request_keepalive = lambda: kept.append(1)
EditorWindow(img(), 1.0, ctx)
cb = QGuiApplication.clipboard().image()
check("fallback: Qt clipboard holds the image", not cb.isNull() and cb.width() == 120 and kept == [1])

cfg = config.load(); cfg.auto_copy = False; config.save(cfg)
check("setting persists", config.load().auto_copy is False)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
