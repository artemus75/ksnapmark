"""Findet vom Nutzer eingegebene Begriffe (Namen, Firmen, Kundennummern …) in OCR-Ergebnissen.

Tolerant gegenüber Groß-/Kleinschreibung, Umlauten (Müller = Mueller = Muller), Satzzeichen
und kleinen OCR-Fehlern. Mehrteilige Namen („Max Mustermann“) werden als Wortfolge gesucht;
auf Wunsch zusätzlich einzelne Namensteile (z. B. nur der Nachname).
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

from PySide6.QtCore import QRectF

from .ocr import Word
from .sensitive import _dedupe

FUZZY_MIN_LEN = 5      # erst ab dieser Länge toleriert die Suche OCR-Fehler
FUZZY_RATIO = 0.84
MIN_PART_LEN = 3       # Namensteile darunter (Initialen, „von“) werden nicht einzeln gesucht


def norm(text: str) -> str:
    """Vergleichsform: kleingeschrieben, ohne Akzente/Umlautpunkte und ohne Satzzeichen."""
    text = text.casefold().replace("ß", "ss")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isalnum() and not unicodedata.combining(c))


def parse_terms(raw: str) -> list[str]:
    """Eingabefeld -> Begriffe (eine Zeile oder Komma/Semikolon getrennt, ohne Doppelte)."""
    terms: list[str] = []
    seen: set[str] = set()
    for chunk in raw.replace(";", "\n").replace(",", "\n").splitlines():
        term = " ".join(chunk.split())
        key = norm(term)
        if len(key) >= 2 and key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def _matches(needle: str, token: str, loose: bool) -> bool:
    """needle (normiert) gegen ein erkanntes Wort. loose=True: Teiltreffer im Wort erlaubt."""
    if not needle or not token:
        return False
    if token == needle:
        return True
    if loose:
        if len(needle) >= MIN_PART_LEN and needle in token:
            return True
    elif len(needle) >= 4 and token.startswith(needle) and len(token) - len(needle) <= 2:
        return True  # „Mustermanns“
    if len(needle) >= FUZZY_MIN_LEN and abs(len(token) - len(needle)) <= 2:
        return SequenceMatcher(None, needle, token).ratio() >= FUZZY_RATIO
    return False


def find_terms(words: list[Word], terms: list[str], parts: bool = True,
               pad: float = 3.0) -> list[tuple[str, QRectF]]:
    """Gibt (Begriff, Rechteck) für jede Fundstelle zurück."""
    lines: dict[tuple[int, int, int], list[Word]] = defaultdict(list)
    for w in words:
        lines[(w.block, w.par, w.line)].append(w)

    found: list[tuple[str, QRectF]] = []
    for line_words in lines.values():
        line_words.sort(key=lambda w: w.num)
        tokens = [(norm(w.text), w) for w in line_words]

        def add(label: str, hit: list[Word]) -> None:
            rect = hit[0].rect
            for w in hit[1:]:
                rect = rect.united(w.rect)
            found.append((label, rect.adjusted(-pad, -pad, pad, pad)))

        for term in terms:
            needles = [n for n in (norm(t) for t in term.split()) if n]
            if not needles:
                continue
            n = len(needles)
            for i in range(len(tokens) - n + 1):
                window = tokens[i:i + n]
                if all(_matches(needles[k], window[k][0], loose=(n == 1)) for k in range(n)):
                    add(term, [w for _t, w in window])
            if parts and n > 1:
                for needle in needles:
                    if len(needle) < MIN_PART_LEN:
                        continue
                    for tok, w in tokens:
                        # lange Namensteile auch mitten im Wort (z. B. in E-Mail-Adressen) finden
                        if _matches(needle, tok, loose=len(needle) >= 5):
                            add(term, [w])
    return _dedupe(found)


def missing_terms(terms: list[str], found: list[tuple[str, QRectF]]) -> list[str]:
    hit = {label for label, _ in found}
    return [t for t in terms if t not in hit]


# --- optionale dauerhafte Liste (Klartextdatei, nur für den Benutzer lesbar) ----------------

def saved_path():
    from .config import CONFIG_DIR

    return CONFIG_DIR / "redact_terms.txt"


def load_saved() -> str:
    try:
        return saved_path().read_text(encoding="utf-8")
    except OSError:
        return ""


def save_saved(raw: str) -> bool:
    import os

    path = saved_path()
    try:
        if not raw.strip():
            path.unlink(missing_ok=True)
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw.strip() + "\n")
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False
