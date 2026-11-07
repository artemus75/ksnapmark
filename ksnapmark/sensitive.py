"""Findet typische sensible Angaben in OCR-Ergebnissen (für das Auto-Schwärzen).

Erkannt werden Muster – keine Namen. Namen und Freitext schwärzt man weiterhin
von Hand mit dem Schwärzen-/Blur-Werkzeug.
"""

from __future__ import annotations

from .i18n import tr

import re
from collections import defaultdict

from PySide6.QtCore import QRectF

from .ocr import Word

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d ()/.-]{7,}\d(?!\w)")
_TOKEN = re.compile(r"\b[A-Za-z0-9_\-+/=]{24,}\b")
_PREFIXED = re.compile(r"\b(?:sk-|ghp_|gho_|github_pat_|xox[bap]-|AKIA|AIza|eyJ)[A-Za-z0-9_\-.]{8,}")
_SECRET_KV = re.compile(r"(?i)\b(?:passwort|password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S+")


def _luhn(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _iban_ok(value: str) -> bool:
    iban = re.sub(r"\s", "", value)
    if not 15 <= len(iban) <= 34:
        return False
    rearranged = iban[4:] + iban[:4]
    try:
        num = "".join(str(int(c, 36)) for c in rearranged)
        return int(num) % 97 == 1
    except ValueError:
        return False


def _ip_ok(value: str) -> bool:
    return all(0 <= int(part) <= 255 for part in value.split("."))


def _token_ok(value: str) -> bool:
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


_DATE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-](?:\d{2}|\d{4})$|^\d{4}-\d{2}-\d{2}$")


def _phone_ok(value: str) -> bool:
    value = value.strip()
    if _DATE.match(value):  # 05.11.2026 ist ein Datum, keine Telefonnummer
        return False
    return sum(c.isdigit() for c in value) >= 8


_RULES = [
    (tr("E-mail"), _EMAIL, None),
    ("IBAN", _IBAN, _iban_ok),
    (tr("IP address"), _IPV4, _ip_ok),
    (tr("Card number"), _CARD, _luhn),
    (tr("Phone number"), _PHONE, _phone_ok),
    (tr("Key/token"), _PREFIXED, None),
    (tr("Key/token"), _TOKEN, _token_ok),
    (tr("Credentials"), _SECRET_KV, None),
]


def find_sensitive(words: list[Word], pad: float = 3.0) -> list[tuple[str, QRectF]]:
    """Gibt (Kategorie, Rechteck) für jede Fundstelle zurück."""
    lines: dict[tuple[int, int, int], list[Word]] = defaultdict(list)
    for w in words:
        lines[(w.block, w.par, w.line)].append(w)

    found: list[tuple[str, QRectF]] = []
    for line_words in lines.values():
        line_words.sort(key=lambda w: w.num)
        text = ""
        spans: list[tuple[int, int, Word]] = []
        for w in line_words:
            if text:
                text += " "
            start = len(text)
            text += w.text
            spans.append((start, len(text), w))
        for label, regex, check in _RULES:
            for m in regex.finditer(text):
                start, end = m.start(), m.end()
                if check:
                    value = m.group(0)
                    # IBAN: ein angehängtes Folgewort wieder abschneiden, falls die Prüfsumme sonst nicht passt
                    while value and not check(value):
                        if label != "IBAN" or " " not in value:
                            value = ""
                            break
                        value = value.rsplit(" ", 1)[0]
                    if not value:
                        continue
                    end = start + len(value)
                hit = [w for s, e, w in spans if s < end and e > start]
                if not hit:
                    continue
                rect = hit[0].rect
                for w in hit[1:]:
                    rect = rect.united(w.rect)
                rect = rect.adjusted(-pad, -pad, pad, pad)
                found.append((label, rect))
    return _dedupe(found)


def _dedupe(found: list[tuple[str, QRectF]]) -> list[tuple[str, QRectF]]:
    result: list[tuple[str, QRectF]] = []
    for label, rect in sorted(found, key=lambda f: -(f[1].width() * f[1].height())):
        if any(r.contains(rect) or r.intersected(rect).width() * r.intersected(rect).height()
               > 0.6 * rect.width() * rect.height() for _, r in result):
            continue
        result.append((label, rect))
    return result
