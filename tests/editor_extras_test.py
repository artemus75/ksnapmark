"""Editor extras: spotlight tool, frame/shadow."""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["KSNAPMARK_LANG"] = "de"
home = tempfile.mkdtemp()
os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["t"])
from ksnapmark.app import Context  # noqa: E402
from ksnapmark.editor import EditorWindow  # noqa: E402
from ksnapmark.frame import BACKGROUNDS, add_frame  # noqa: E402
from ksnapmark.items import Item, hit_test, render  # noqa: E402

res = []


def check(n, c, extra=""):
    res.append(bool(c)); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra and not c else ""))


def white(w=300, h=200):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    return img


def px(img, x, y):
    return QColor(img.pixel(x, y))


# --- spotlight -------------------------------------------------------------------------------
spot = Item(kind="spot", p1=QPointF(100, 50), p2=QPointF(200, 120))
out = render(white(), [spot])
check("spotlight: inside stays bright", px(out, 150, 80).name() == "#ffffff")
check("spotlight: outside is dimmed", px(out, 10, 10).lightness() < 140 and px(out, 280, 190).lightness() < 140)
check("spotlight: hit test inside the box", hit_test(spot, QPointF(150, 80), 4) and not hit_test(spot, QPointF(10, 10), 4))

ed = EditorWindow(white(), 1.0, Context(), record=False)
ed.show()
check("spotlight tool exists (S)", "spot" in ed.tool_actions and ed.tool_actions["spot"].shortcut().toString() == "S")
ed.set_tool("spot")
c = ed.canvas


def drag(a, b, steps=5):
    QTest.mousePress(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*a))
    for i in range(1, steps + 1):
        QTest.mouseMove(c, QPoint(round(a[0] + (b[0] - a[0]) * i / steps), round(a[1] + (b[1] - a[1]) * i / steps)))
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*b))


drag((60, 40), (160, 100))
check("spotlight drawn in the editor", len(c.items) == 1 and c.items[0].kind == "spot")
r = c.result_image()
check("result: dimmed outside, bright inside", px(r, 100, 70).name() == "#ffffff" and px(r, 250, 180).lightness() < 140)
ed.set_tool("select")
QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 70))
check("spotlight can be selected", c.selected is not None and c.selected.kind == "spot")

# --- frame ---------------------------------------------------------------------------------------
img = white(200, 100)
fr = add_frame(img, padding=40, background="dark", radius=10, shadow=True)
check("frame: size grows by the padding", (fr.width(), fr.height()) == (280, 180), str(fr.size()))
check("frame: background color in the corner", px(fr, 2, 2).name() == "#1e1f26")
check("frame: image in the middle", px(fr, 140, 90).name() == "#ffffff")
check("frame: rounded corner is not image-white", px(fr, 40, 40).name() != "#ffffff")
check("frame: shadow darkens below the image", px(fr, 140, 145).lightness() < px(fr, 140, 5).lightness() + 1 and px(fr, 140, 145).name() != "#1e1f26")
tr_ = add_frame(img, padding=30, background="transparent", radius=8, shadow=False)
check("frame: transparent background", QColor.fromRgba(tr_.pixel(1, 1)).alpha() == 0)
no = add_frame(img, padding=0, background="ocean", radius=0, shadow=True)
check("frame: padding 0 keeps the size", no.size() == img.size())
check("frame: gradient differs between corners", px(add_frame(img, 40, "ocean", 0, False), 1, 1).name()
      != px(add_frame(img, 40, "ocean", 0, False), 277, 177).name())
check("frame: all backgrounds render", all(add_frame(img, 20, k, 6, True).width() == 240 for k in BACKGROUNDS))

before = (c.base.width(), c.base.height())
c.apply_frame(padding=24, background="white", radius=6, shadow=False)
check("canvas: frame applied and items flattened", c.base.width() == before[0] + 48 and c.items == [])
c.undo()
check("canvas: frame is undoable", (c.base.width(), c.base.height()) == before and len(c.items) == 1)

from ksnapmark.dialogs import FrameDialog  # noqa: E402
dlg = FrameDialog(white(400, 250))
dlg.padding.setValue(60); dlg.background.setCurrentIndex(dlg.background.findData("sunset")); dlg.shadow.setChecked(False)
o = dlg.options()
check("dialog options", o == {"padding": 60, "background": "sunset", "radius": 12, "shadow": False}, str(o))
check("dialog preview is drawn", not dlg.preview.pixmap().isNull())
check("editor has the frame button", ed.act_frame is not None)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
