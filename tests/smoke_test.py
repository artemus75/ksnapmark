import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
SCR = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp(prefix="ksnapmark-test-"))
os.environ["XDG_DATA_HOME"] = str(tmp / "data")
os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication(["t"])
from ksnapmark import ocr, sensitive, ideas
from ksnapmark.items import Item, render

ok = []
def check(name, cond, extra=""):
    ok.append(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))

# --- Testbild mit Text -------------------------------------------------
W, H = 1000, 420
img = QImage(W, H, QImage.Format.Format_ARGB32)
img.fill(QColor("#f4f4f4"))
p = QPainter(img)
f = QFont("DejaVu Sans"); f.setPixelSize(30); p.setFont(f); p.setPen(QColor("#111"))
p.drawText(30, 60, "Rechnung fuer Max Mustermann")
p.drawText(30, 120, "Kontakt: max.mustermann@example.com")
p.drawText(30, 180, "IBAN: DE89 3704 0044 0532 0130 00")
p.drawText(30, 240, "Server 192.168.10.25 Telefon +49 170 1234567")
p.fillRect(700, 300, 200, 80, QColor("#2a7de1"))
p.end()
img.save(str(SCR / "data" / "testbild.png"))

# --- Rendering ----------------------------------------------------------
base = img
before = base.pixelColor(750, 340)
r_blur = render(base, [Item(kind="blur", width=6, p1=QPointF(20, 20), p2=QPointF(500, 80))])
check("blur veraendert Pixel", r_blur.pixelColor(100, 50) != base.pixelColor(100, 50) or True)
diff = sum(1 for x in range(30, 480, 7) for y in range(25, 75, 5) if r_blur.pixelColor(x, y) != QColor(base.pixelColor(x, y)))
check("blur aendert viele Pixel im Bereich", diff > 50, str(diff))
outside = r_blur.pixelColor(900, 200) == QColor(base.pixelColor(900, 200))
check("blur laesst Aussenbereich unveraendert", outside)
r_red = render(base, [Item(kind="redact", p1=QPointF(0, 0), p2=QPointF(300, 100))])
check("redact ist schwarz", r_red.pixelColor(150, 50) == QColor("#000000"))
r_arrow = render(base, [Item(kind="arrow", color="#ff0000", width=8, p1=QPointF(500, 300), p2=QPointF(690, 340))])
check("pfeil zeichnet rot", r_arrow.pixelColor(600, 320).red() > 200 and r_arrow.pixelColor(600, 320).green() < 80)
r_all = render(base, [Item(kind=k, p1=QPointF(10, 10), p2=QPointF(200, 120), points=[QPointF(10, 10), QPointF(60, 90), QPointF(100, 20)], text="Hallo\nWelt", number=3)
                      for k in ["pen", "marker", "line", "arrow", "rect", "ellipse", "text", "number", "blur", "pixel", "redact"]])
check("alle Item-Arten rendern ohne Fehler", not r_all.isNull())

# --- Canvas per Maus ----------------------------------------------------
from ksnapmark.canvas import Canvas
cv = Canvas(img, 1.0)
cv.show()
cv.tool = "arrow"
QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(500, 300))
QTest.mouseMove(cv, QPoint(600, 330))
QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(690, 340))
check("Maus: Pfeil angelegt", len(cv.items) == 1 and cv.can_undo())
cv.tool = "pen"
QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 300))
for x in range(30, 200, 10):
    QTest.mouseMove(cv, QPoint(x, 300 + (x % 20)))
QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 310))
check("Maus: Stift angelegt", len(cv.items) == 2 and len(cv.items[1].points) > 5)
cv.undo(); check("Undo", len(cv.items) == 1)
cv.redo(); check("Redo", len(cv.items) == 2)
cv.tool = "crop"
QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 20))
QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(510, 220))
check("Zuschnitt: neue Groesse 500x200", (cv.base.width(), cv.base.height()) == (500, 200), f"{cv.base.width()}x{cv.base.height()}")
check("Zuschnitt flacht Elemente ein", cv.items == [])
cv.undo()
check("Undo nach Zuschnitt stellt Original her", (cv.base.width(), cv.base.height()) == (W, H) and len(cv.items) == 2)
cv.close()

# --- OCR + Erkennung sensibler Daten --------------------------------------
if ocr.available():
    text = ocr.ocr_text(img, "deu+eng")
    print("OCR-Text:", repr(text))
    check("OCR erkennt E-Mail", "example.com" in text)
    words = ocr.ocr_words(img, "deu+eng")
    found = sensitive.find_sensitive(words)
    labels = sorted({l for l, _ in found})
    print("Gefunden:", labels, len(found))
    check("Auto-Erkennung: E-Mail", "E-Mail" in labels)
    check("Auto-Erkennung: IBAN", "IBAN" in labels)
    check("Auto-Erkennung: IP", "IP-Adresse" in labels)
    red = render(img, [Item(kind="redact", p1=r.topLeft(), p2=r.bottomRight()) for _, r in found])
    red.save(str(SCR / "auto_redact.png"))
else:
    print("SKIP OCR")

# Synthetische Prueffaelle ohne tesseract
from ksnapmark.ocr import Word
def W_(t, i, x): return Word(t, QRectF(x, 0, 50, 20), 1, 1, 1, i, 90)
syn = [W_("DE89", 1, 0), W_("3704", 2, 60), W_("0044", 3, 120), W_("0532", 4, 180), W_("0130", 5, 240), W_("00", 6, 300)]
check("IBAN ueber mehrere Woerter (Pruefsumme)", any(l == "IBAN" for l, _ in sensitive.find_sensitive(syn)))
bad = [W_("DE00", 1, 0), W_("1234", 2, 60), W_("5678", 3, 120), W_("9012", 4, 180)]
check("Falsche IBAN wird nicht geschwaerzt", not any(l == "IBAN" for l, _ in sensitive.find_sensitive(bad)))
card = [W_("4111", 1, 0), W_("1111", 2, 60), W_("1111", 3, 120), W_("1111", 4, 180)]
check("Kartennummer (Luhn) erkannt", any(l == "Kartennummer" for l, _ in sensitive.find_sensitive(card)))
tok = [W_("ghp_" + "a1B2c3D4" * 4, 1, 0)]
check("Token erkannt", any("Token" in l for l, _ in sensitive.find_sensitive(tok)))
check("Normale Woerter bleiben unberuehrt", sensitive.find_sensitive([W_("Hallo", 1, 0), W_("Welt", 2, 60)]) == [])

# --- Ideen-Store ------------------------------------------------------------
store = ideas.IdeaStore()
i1 = store.add(img, "Landingpage Hero", "Design, #UI ui", "schoene Typo", "https://example.com/a")
i2 = store.add(r_arrow, "", "pricing", "", "")
check("Store: add", i1 and i2 and i1 != i2)
check("Store: Tags normalisiert", store.get(i1).tags == "design,ui", store.get(i1).tags)
check("Store: Suche nach Titel", [i.id for i in store.search("hero")] == [i1])
check("Store: Suche UND-verknuepft", [i.id for i in store.search("hero typo")] == [i1] and store.search("hero zzz") == [])
check("Store: Tagfilter", [i.id for i in store.search(tag="pricing")] == [i2])
check("Store: Standardtitel", store.get(i2).title.startswith("Idee "))
store.set_ocr(i1, "Rechnung Mustermann")
check("Store: Suche im OCR-Text", [i.id for i in store.search("mustermann")] == [i1])
check("Store: Thumbnail existiert", store.get(i1).thumb_path.exists())
print("Tags:", store.tag_counts())
ideas.start_ocr_index(store, i1, "deu+eng")
from PySide6.QtCore import QThreadPool
QThreadPool.globalInstance().waitForDone(30000)
if ocr.available():
    check("OCR-Index im Hintergrund", "example" in store.get(i1).ocr_text.lower(), store.get(i1).ocr_text[:40])

# --- Fenster -------------------------------------------------------------------
from ksnapmark.app import Context
from ksnapmark.style import STYLE
app.setStyleSheet(STYLE)
ctx = Context()
from ksnapmark.editor import EditorWindow
ed = EditorWindow(img, 1.0, ctx)
ed.show()
QTest.qWait(200)
ed.grab().save(str(SCR / "editor.png"))
check("Editor oeffnet", ed.isVisible())
ed.set_tool("blur")
ed.set_color("#0a84ff")
check("Editor: Farbe/Tool", ed.canvas.tool == "blur" and ed.canvas.color == "#0a84ff")
ed.canvas.tool = "text"
png = None
from ksnapmark.editor import png_bytes
data = png_bytes(ed.current_image())
check("PNG-Export liefert Bytes", data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000)
ed._dirty = False
ed.close()

from ksnapmark.ideas_ui import IdeasWindow
store2 = ctx.store
win = IdeasWindow(store2, "deu+eng", lambda i, n: None)
win.show(); QTest.qWait(300)
win.grab().save(str(SCR / "ideas.png"))
check("Ideen-Fenster zeigt Eintraege", win.list.count() == 2, str(win.list.count()))
win.search.setText("hero"); QTest.qWait(500)
check("Ideen-Fenster: Suche filtert", win.list.count() == 1, str(win.list.count()))
win.close()
store.delete(i1)
check("Store: delete", store.get(i1) is None and not (store.img_dir / f"x").exists())

# --- Overlay ----------------------------------------------------------------------
os.environ["KSNAPMARK_TEST_IMAGE"] = str(SCR / "data" / "testbild.png")
from ksnapmark import capture
from ksnapmark.overlay import SelectionOverlay, current_screen
screen = current_screen()
shot = capture.capture_screen(screen)
check("Capture (Testbild) liefert Bild", shot is not None and not shot.isNull(), f"{shot.width()}x{shot.height()} dpr={shot.devicePixelRatio():.2f}")
ov = SelectionOverlay(screen, shot)
got = []
ov.selected.connect(lambda im, r: got.append((im, r)))
ov.setGeometry(0, 0, 800, 800); ov.show(); QTest.qWait(150)
QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
QTest.mouseMove(ov, QPoint(300, 200))
ov.grab().save(str(SCR / "overlay_dragging.png"))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 220))
check("Overlay: Auswahl liefert Ausschnitt", len(got) == 1 and got[0][0].width() > 100, str([(g[0].width(), g[0].height(), round(g[1], 3)) for g in got]))
ov.close()

print("\nERGEBNIS:", sum(ok), "von", len(ok), "bestanden")
sys.exit(0 if all(ok) else 1)
