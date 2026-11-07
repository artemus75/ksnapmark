"""Select tool: pick, move, resize, recolor, delete, nudge, undo, non-destructive rendering."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["KSNAPMARK_LANG"] = "de"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = Path(tempfile.mkdtemp(prefix="ksnapmark-test-"))
os.environ["XDG_DATA_HOME"] = str(tmp / "data")
os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["t"])
from ksnapmark.canvas import Canvas  # noqa: E402
from ksnapmark.items import Item, hit_test, item_bounds  # noqa: E402

res = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info and not ok else ""))
    res.append(bool(ok))


def new_canvas():
    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    c = Canvas(img, 1.0)
    c.show()
    return c


def drag(c, a, b, steps=6):
    w = c
    QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*a))
    for i in range(1, steps + 1):
        x = a[0] + (b[0] - a[0]) * i / steps
        y = a[1] + (b[1] - a[1]) * i / steps
        QTest.mouseMove(w, QPoint(round(x), round(y)))
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*b))


def click(c, pt):
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*pt))


# --- hit tests ---------------------------------------------------------------------------
rect = Item(kind="rect", width=4, p1=QPointF(50, 50), p2=QPointF(150, 100))
check("hit: rectangle outline", hit_test(rect, QPointF(50, 75), 4))
check("hit: empty inside of an unfilled rectangle is not a hit", not hit_test(rect, QPointF(100, 75), 4))
rect.filled = True
check("hit: filled rectangle interior", hit_test(rect, QPointF(100, 75), 4))
check("hit: far away", not hit_test(rect, QPointF(300, 200), 4))
ell = Item(kind="ellipse", width=4, p1=QPointF(0, 0), p2=QPointF(100, 60))
check("hit: ellipse outline", hit_test(ell, QPointF(100, 30), 4))
check("hit: ellipse center (unfilled) is not a hit", not hit_test(ell, QPointF(50, 30), 4))
pen = Item(kind="pen", width=4, points=[QPointF(10, 10), QPointF(60, 10), QPointF(60, 60)])
check("hit: pen stroke", hit_test(pen, QPointF(35, 11), 4) and hit_test(pen, QPointF(60, 40), 4))
check("hit: beside the pen stroke", not hit_test(pen, QPointF(35, 40), 4))
arrow = Item(kind="arrow", width=6, p1=QPointF(10, 10), p2=QPointF(110, 10))
check("hit: arrow shaft and tip", hit_test(arrow, QPointF(60, 12), 4) and hit_test(arrow, QPointF(108, 10), 4))
text = Item(kind="text", width=6, p1=QPointF(20, 20), text="Hallo Welt")
b = item_bounds(text)
check("text bounds have a sensible size", b.width() > 40 and b.height() > 10, str(b))
check("hit: text", hit_test(text, QPointF(b.center().x(), b.center().y()), 4))
num = Item(kind="number", width=6, p1=QPointF(30, 30), number=1)
check("hit: number badge", hit_test(num, QPointF(32, 31), 4) and not hit_test(num, QPointF(80, 80), 4))

# --- select, move, undo --------------------------------------------------------------------
c = new_canvas()
c.set_tool("rect")
drag(c, (50, 50), (150, 100))
check("rectangle drawn", len(c.items) == 1)
c.set_tool("select")
undo_before = len(c._undo)
click(c, (100, 75))
check("click inside an unfilled rectangle does not select it", c.selected is None)
click(c, (50, 75))
check("click on the outline selects it", c.selected is c.items[0])
check("a plain click adds no undo step", len(c._undo) == undo_before)
orig = c.items[0]
drag(c, (50, 75), (80, 125))
moved = c.items[0]
check("drag moved the item by the mouse delta",
      abs(moved.p1.x() - 80) < 1.5 and abs(moved.p1.y() - 100) < 1.5, f"{moved.p1}")
check("exactly one undo step for the whole drag", len(c._undo) == undo_before + 1)
check("the original item object was left untouched (undo-safe)",
      abs(orig.p1.x() - 50) < 0.01 and abs(orig.p1.y() - 50) < 0.01)
check("selection follows the moved item", c.selected is c.items[0])
c.undo()
check("undo restores the old position", abs(c.items[0].p1.x() - 50) < 0.01 and c.selected is None)
c.redo()
check("redo moves it again", abs(c.items[0].p1.x() - 80) < 1.5)

# --- resize ------------------------------------------------------------------------------------
click(c, (80, 125))  # re-select: outline of the moved rectangle (left edge, middle)
check("re-selected after redo", c.selected is c.items[0])
br = c.items[0].rect().bottomRight()
drag(c, (round(br.x()), round(br.y())), (round(br.x()) + 40, round(br.y()) + 30))
r = c.items[0].rect()
check("bottom-right handle resizes", abs(r.width() - 140) < 2 and abs(r.height() - 80) < 2, str(r))
check("top-left corner stays put", abs(r.left() - 80) < 1.5)

# --- recolor / width via apply_to_selected ---------------------------------------------------
n = len(c._undo)
check("apply color", c.apply_to_selected(color="#00ff00") and c.items[0].color == "#00ff00")
check("one undo step per property change", len(c._undo) == n + 1)
check("same value again changes nothing", not c.apply_to_selected(color="#00ff00") and len(c._undo) == n + 1)
c.apply_to_selected(width=10)
check("apply width (scaled by dpr)", c.items[0].width == 10)
c.undo()
check("undo of the width change", c.items[0].width == 6 and c.items[0].color == "#00ff00")

# --- nudge and delete via keyboard -----------------------------------------------------------
click(c, (round(c.items[0].p1.x()), round((c.items[0].p1.y() + c.items[0].p2.y()) / 2)))
check("reselected after undo", c.selected is not None)
x0 = c.items[0].p1.x()
QTest.keyClick(c, Qt.Key.Key_Right)
QTest.keyClick(c, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
check("arrow keys nudge (1 px, Shift = 10 px)", abs(c.items[0].p1.x() - (x0 + 11)) < 0.01)
QTest.keyClick(c, Qt.Key.Key_Delete)
check("Delete removes the selected item", len(c.items) == 0 and c.selected is None)
c.undo()
check("undo brings it back", len(c.items) == 1)

# --- deselect by clicking empty space / switching tool ---------------------------------------
click(c, (c.items[0].p1.x().__int__() + 20, c.items[0].p1.y().__int__()))
check("selected again", c.selected is not None)
click(c, (380, 280))
check("click on empty space deselects", c.selected is None)
click(c, (c.items[0].p1.x().__int__() + 20, c.items[0].p1.y().__int__()))
c.set_tool("pen")
check("switching to a drawing tool clears the selection", c.selected is None)

# --- non-destructive: moving an effect restores the pixels underneath ---------------------------
d = new_canvas()
d.set_tool("redact")
drag(d, (20, 20), (80, 60))
d.set_tool("select")
before = d.result_image()
check("redact covers the area", QColor(before.pixel(40, 40)).name() == "#000000")
click(d, (50, 40))
drag(d, (50, 40), (250, 140))
after = d.result_image()
check("old place is white again", QColor(after.pixel(40, 40)).name() == "#ffffff")
check("new place is covered", QColor(after.pixel(270, 140)).name() == "#000000")

# --- numbers are renumbered after a delete -----------------------------------------------------
e = new_canvas()
e.set_tool("number")
for pt in ((50, 50), (150, 50), (250, 50)):
    click(e, pt)
e.set_tool("select")
click(e, (150, 50))
check("select number 2", e.selected is not None and e.selected.number == 2)
e.delete_selected()
check("numbers stay gap-free (1, 2)", [i.number for i in e.items] == [1, 2], str([i.number for i in e.items]))

# --- editor integration ------------------------------------------------------------------------
from ksnapmark.app import Context  # noqa: E402
from ksnapmark.editor import EditorWindow  # noqa: E402

img = QImage(500, 300, QImage.Format.Format_ARGB32)
img.fill(QColor("#ffffff"))
ed = EditorWindow(img, 1.0, Context(), record=False)
ed.show()
check("Select tool exists with shortcut V", "select" in ed.tool_actions and ed.tool_actions["select"].shortcut().toString() == "V")
ed.set_tool("rect")
ed.set_color("#0a84ff")
ed.slider.setValue(8)
drag(ed.canvas, (60, 60), (200, 140))
ed.set_tool("select")
ed.set_color("#ff9500")
check("color change before selecting does not touch the item", ed.canvas.items[0].color == "#0a84ff")
click(ed.canvas, (60, 100))
check("selecting shows the item's color in the toolbar", ed.canvas.color == "#0a84ff" and ed.slider.value() == 8)
ed.set_color("#bf5af2")
check("toolbar color applies to the selected item", ed.canvas.items[0].color == "#bf5af2")
ed.slider.setValue(14)
check("slider applies to the selected item", ed.canvas.items[0].width == 14)
ed.fill_box.setChecked(True)
check("fill checkbox applies to the selected rectangle", ed.canvas.items[0].filled is True)
ed._escape()
check("Esc clears the selection first", ed.canvas.selected is None and ed.isVisible())
print("ERGEBNIS:", sum(res), "von", len(res))
sys.exit(0 if all(res) else 1)
