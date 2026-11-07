import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
app = QApplication(["t"])
from ksnapmark import findtext, ocr
from ksnapmark.ocr import Word
from ksnapmark.items import render, Item

res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))

# --- reine Logik mit künstlichen Wörtern
def W(t, x, num, line=0): return Word(t, QRectF(x, 10 + line * 30, 60, 20), 1, 1, line, num, 90)
ws = [W("Rechnung", 0, 1), W("für", 70, 2), W("Max", 140, 3), W("Mustermann,", 210, 4),
      W("Müller", 0, 1, 1), W("GmbH", 70, 2, 1), W("m.mustermann@example.com", 140, 3, 1), W("Mustermamn", 0, 1, 2)]
hits = findtext.find_terms(ws, ["Max Mustermann"], parts=False)
check("Vollname als Wortfolge", len(hits) == 1 and hits[0][1].width() > 100, str(len(hits)))
hits = findtext.find_terms(ws, ["Max Mustermann"], parts=True)
check("Namensteile: Nachname zusätzlich (Zeile 3 + Zeile 1)", len(hits) >= 2, str(len(hits)))
check("Teil 'Max' trifft nicht 'Maximum'", not findtext.find_terms([W("Maximum", 0, 1)], ["Max Mustermann"], parts=True))
check("Umlaut: 'Mueller' findet 'Müller'", len(findtext.find_terms(ws, ["Mueller"])) == 1)
check("Gross/Klein egal", len(findtext.find_terms(ws, ["GMBH"])) == 1)
check("Einzelwort als Teilstring in E-Mail", any(r.x() >= 139 for _l, r in findtext.find_terms(ws, ["mustermann"], parts=False)))
check("OCR-Fehler toleriert (Mustermamn)", any(r.y() > 60 for _l, r in findtext.find_terms(ws, ["Mustermann"], parts=False)))
check("kurzer Begriff nur exakt", not findtext.find_terms([W("Anna", 0, 1)], ["An"]) and len(findtext.find_terms([W("An", 0, 1)], ["An"])) == 1)
check("nichts gefunden -> missing", findtext.missing_terms(["Xyz Abc"], findtext.find_terms(ws, ["Xyz Abc"])) == ["Xyz Abc"])
check("parse_terms", findtext.parse_terms("Max Mustermann\n\n max  mustermann ; ACME, A") == ["Max Mustermann", "ACME"])

# --- Ende-zu-Ende mit echter Texterkennung
if ocr.available():
    img = QImage(900, 260, QImage.Format.Format_RGB32); img.fill(QColor("white"))
    p = QPainter(img); f = QFont("DejaVu Sans"); f.setPixelSize(26); p.setFont(f); p.setPen(QColor("black"))
    p.drawText(20, 50, "Rechnung für Max Mustermann")
    p.drawText(20, 100, "Kontakt: m.mustermann@example.com")
    p.drawText(20, 150, "Firma: Müller Systemtechnik GmbH")
    p.drawText(20, 200, "Bestellung 4711 vom 05.11.2026")
    p.end()
    words = ocr.ocr_words(img, "deu+eng")
    terms = ["Max Mustermann", "Mueller", "Nichtda Person"]
    hits = findtext.find_terms(words, terms)
    check("OCR: Treffer gefunden", len(hits) >= 3, f"{len(hits)} Treffer; Wörter: {[w.text for w in words][:12]}")
    check("OCR: nicht vorhandener Begriff wird gemeldet", findtext.missing_terms(terms, hits) == ["Nichtda Person"])
    for kind in ("blur", "pixel", "redact"):

        items = []
        for _l, r in hits:
            width = max(2.0, r.height() / 4.0) if kind != "redact" else 2.0
            items.append(Item(kind=kind, width=width, p1=r.topLeft(), p2=r.bottomRight(), unit=1.0))
        out = render(img, items)
        left = findtext.find_terms(ocr.ocr_words(out, "deu+eng"), ["Max Mustermann", "Mueller"])
        check(f"nach {kind}: Namen nicht mehr lesbar", len(left) == 0, f"{len(left)} übrig")
    out = render(img, [Item(kind="blur", width=2.0, p1=r.topLeft(), p2=r.bottomRight(), unit=1.0) for _l, r in hits])
    out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "findtext_blur.png"))
    keep = ocr.ocr_text(out, "deu+eng")
    check("Rest bleibt lesbar (Bestellung 4711)", "4711" in keep, keep.replace("\n", " | ")[:100])
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
