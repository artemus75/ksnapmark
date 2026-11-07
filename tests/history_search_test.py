"""Searchable history: index storage, search, dialog with background indexing (fake OCR)."""
import os
import stat
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["KSNAPMARK_LANG"] = "de"
home = tempfile.mkdtemp()
os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["t"])
from ksnapmark import config, ocr  # noqa: E402
from ksnapmark.history import History  # noqa: E402
from ksnapmark.history_ui import HistoryDialog  # noqa: E402

res = []


def check(n, c, extra=""):
    res.append(bool(c)); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra and not c else ""))


def img(c):
    i = QImage(200, 120, QImage.Format.Format_RGB32); i.fill(QColor(c)); return i


def wait(cond, ms=5000):
    t = time.monotonic()
    while not cond() and time.monotonic() - t < ms / 1000:
        app.processEvents(); QTest.qWait(10)
    return cond()


d = tempfile.mkdtemp()
h = History(10, __import__("pathlib").Path(d))
names = []
for c in ("red", "green", "blue"):
    names.append(h.add(img(c))); time.sleep(0.01)
check("new entries have no index yet", len(h.missing()) == 3 and h.text_of(names[0]) is None)
h.set_text(names[0], "Rechnung Nr. 4711\nSumme 120,50 EUR")
h.set_text(names[1], "Fehlermeldung: Verbindung abgelehnt")
check("missing shrinks", [e.name for e in h.missing()] == [names[2]])
check("index file is private", stat.S_IMODE(h.index_path.stat().st_mode) == 0o600 and stat.S_IMODE(h.dir.stat().st_mode) == 0o700)
check("search: case-insensitive word", [e.name for e in h.search("rechnung")] == [names[0]])
check("search: all words must match", [e.name for e in h.search("fehlermeldung abgelehnt")] == [names[1]]
      and h.search("rechnung abgelehnt") == [])
check("search: empty query returns all, newest first", [e.name for e in h.search("")] == names[::-1])
check("search: unindexed entries never match", names[2] not in [e.name for e in h.search("rot")])
h2 = History(10, __import__("pathlib").Path(d))
check("index survives a restart", h2.text_of(names[0]).startswith("Rechnung"))
had = h.text_of(names[0]) is not None
new_name = h.add(img("yellow"), replace=names[0])
check("replacing an entry drops its stale text", had and new_name != names[0] and h.text_of(names[0]) is None)
names[0] = h.entries()[0].name
check("delete removes image and text", h.delete(names[1]) and h.text_of(names[1]) is None
      and names[1] not in [e.name for e in h.entries()])
check("delete rejects odd names", not h.delete("../../etc/passwd"))
small = History(2, __import__("pathlib").Path(d))
h.set_text(names[2], "alt")
small.add(img("white")); time.sleep(0.01); small.add(img("black"))
check("prune also drops the index of removed images", names[2] not in small._load_index() and len(small.entries()) == 2)
check("clear removes the index", (small.clear() >= 0) and not small.index_path.exists() and small.search("alt") == [])

# --- dialog ------------------------------------------------------------------------------------
fake_texts = {}
calls = []


def fake_ocr(image, langs="deu+eng"):
    calls.append(image.pixelColor(5, 5).name())
    return fake_texts.get(image.pixelColor(5, 5).name(), "")


ocr.available = lambda: True
ocr.ocr_text = fake_ocr
fake_texts.update({"#ff0000": "Rechnung 2026 Telekom", "#008000": "Fehler im Log: timeout", "#0000ff": "Rechnung Strom"})
hist = History(10, __import__("pathlib").Path(tempfile.mkdtemp()))
for c in ("red", "green", "blue"):
    hist.add(img(c)); time.sleep(0.01)
dlg = HistoryDialog(hist, "deu+eng", True)
dlg.show()
check("dialog lists all entries at first", dlg.list.count() == 3)
check("background indexing completes", wait(lambda: not hist.missing()), str(len(hist.missing())))
check("every image was recognized once", sorted(calls) == ["#0000ff", "#008000", "#ff0000"], str(calls))
dlg.search.setText("rechnung")
check("search filters the thumbnails", dlg.list.count() == 2, str(dlg.list.count()))
check("status shows the count", "2 von 3" in dlg.status.text(), dlg.status.text())
dlg.search.setText("timeout")
check("search finds the other one", dlg.list.count() == 1)
dlg.search.setText("gibtesnicht")
check("no match: empty list, buttons disabled", dlg.list.count() == 0 and not dlg.open_btn.isEnabled())
dlg.search.setText("")
check("clearing the search shows everything", dlg.list.count() == 3)
opened = []
dlg.open_entry.connect(opened.append)
dlg.list.setCurrentRow(1)
want = dlg.selected_name()
dlg.open_selected()
check("open emits the entry name", opened == [want])
dlg.delete_selected()
check("delete removes the selected entry", dlg.list.count() == 2 and want not in [e.name for e in hist.entries()])

# dialog without OCR index (setting off)
calls.clear()
hist2 = History(10, __import__("pathlib").Path(tempfile.mkdtemp())); hist2.add(img("red"))
dlg2 = HistoryDialog(hist2, "deu+eng", False)
app.processEvents(); QTest.qWait(50)
check("setting off: nothing is indexed", calls == [] and len(hist2.missing()) == 1)
# closing stops indexing
hist3 = History(10, __import__("pathlib").Path(tempfile.mkdtemp()))
for c in ("red", "green", "blue"):
    hist3.add(img(c)); time.sleep(0.01)
dlg3 = HistoryDialog(hist3, "deu+eng", True)
dlg3.close(); QTest.qWait(200)
check("closing the dialog stops indexing", len(hist3.missing()) >= 1)

check("config option exists", config.Config(save_dir=__import__("pathlib").Path("/tmp")).history_ocr is True)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
