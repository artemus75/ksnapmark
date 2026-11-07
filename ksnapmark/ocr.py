"""Texterkennung über die tesseract-CLI."""

from __future__ import annotations

from .i18n import tr

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage


class OcrError(RuntimeError):
    pass


@dataclass
class Word:
    text: str
    rect: QRectF
    block: int
    par: int
    line: int
    num: int
    conf: float


MISSING_HINT = (tr("Tesseract is not installed.\n\nInstall on Arch:\nsudo pacman -S tesseract tesseract-data-deu tesseract-data-eng"))


def available() -> bool:
    return shutil.which("tesseract") is not None


def installed_langs() -> list[str]:
    exe = shutil.which("tesseract")
    if not exe:
        return []
    try:
        res = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    lines = (res.stdout or res.stderr).splitlines()
    return [ln.strip() for ln in lines[1:] if ln.strip() and ln.strip() != "osd"]


def pick_langs(preferred: str) -> str:
    installed = installed_langs()
    chosen = [lang for lang in preferred.split("+") if lang in installed]
    if not chosen:
        if "eng" in installed:
            chosen = ["eng"]
        elif installed:
            chosen = [installed[0]]
    return "+".join(chosen) or "eng"


def _prepare(img: QImage, directory: Path) -> tuple[Path, float]:
    """Kleine Schrift erkennt tesseract deutlich besser, wenn das Bild größer ist."""
    factor = 1.0
    if img.width() < 2400 and img.height() < 2400:
        factor = 2.0
    prepared = img
    if factor != 1.0:
        prepared = img.scaled(int(img.width() * factor), int(img.height() * factor),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    prepared = prepared.convertToFormat(QImage.Format.Format_Grayscale8)
    path = directory / "ocr.png"
    if not prepared.save(str(path), "PNG"):
        raise OcrError(tr("The image could not be prepared for text recognition."))
    return path, factor


def _run(args: list[str]) -> str:
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise OcrError(tr("Text recognition took too long.")) from exc
    if res.returncode != 0:
        raise OcrError(res.stderr.strip() or "tesseract ist fehlgeschlagen.")
    return res.stdout


def ocr_text(img: QImage, langs: str = "deu+eng") -> str:
    exe = shutil.which("tesseract")
    if not exe:
        raise OcrError(MISSING_HINT)
    with tempfile.TemporaryDirectory(prefix="ksnapmark-ocr-") as d:
        path, _ = _prepare(img, Path(d))
        out = _run([exe, str(path), "stdout", "-l", pick_langs(langs),
                    "-c", "preserve_interword_spaces=1"])
    return out.strip("\n").strip()


def ocr_words(img: QImage, langs: str = "deu+eng") -> list[Word]:
    exe = shutil.which("tesseract")
    if not exe:
        raise OcrError(MISSING_HINT)
    with tempfile.TemporaryDirectory(prefix="ksnapmark-ocr-") as d:
        path, factor = _prepare(img, Path(d))
        out = _run([exe, str(path), "stdout", "-l", pick_langs(langs), "tsv"])
    return parse_tsv(out, factor)


def parse_tsv(tsv: str, factor: float = 1.0) -> list[Word]:
    words: list[Word] = []
    for line in tsv.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        try:
            conf = float(cols[10])
            left, top, w, h = (float(cols[i]) / factor for i in (6, 7, 8, 9))
            block, par, ln, num = (int(cols[i]) for i in (2, 3, 4, 5))
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append(Word(text, QRectF(left, top, w, h), block, par, ln, num, conf))
    return words
