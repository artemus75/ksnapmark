"""QR-Codes und Strichcodes im Bild lesen.

Bevorzugt ``zbarimg`` (Arch: ``sudo pacman -S zbar``, liest QR und viele Strichcode-Arten);
ohne zbar dient OpenCV (``python-opencv``) als Rückfall, das nur QR-Codes kennt.
"""

from __future__ import annotations

from .i18n import tr

import base64
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

MISSING_HINT = (tr("A program for reading QR codes is missing.\n\nInstall on Arch:\nsudo pacman -S zbar\n\n(Alternatively: sudo pacman -S python-opencv – but that reads QR codes only.)"))


class QrError(RuntimeError):
    pass


@dataclass
class Code:
    kind: str   # z. B. "QR-Code", "EAN-13"
    data: str


def backend() -> str | None:
    if shutil.which("zbarimg"):
        return "zbar"
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        return "opencv"
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    return backend() is not None


def decode(img: QImage) -> list[Code]:
    """Alle Codes im Bild; leere Liste, wenn keiner gefunden wurde."""
    which = backend()
    if which is None:
        raise QrError(MISSING_HINT)
    codes = _decode_zbar(img) if which == "zbar" else _decode_opencv(img)
    seen: set[tuple[str, str]] = set()
    unique = []
    for c in codes:
        if (c.kind, c.data) not in seen:
            seen.add((c.kind, c.data))
            unique.append(c)
    return unique


# --- zbar ---------------------------------------------------------------------------------

def parse_zbar_xml(xml_text: str) -> list[Code]:
    codes: list[Code] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return codes
    for sym in root.iter():
        if not sym.tag.endswith("symbol"):
            continue
        data_el = next((c for c in sym if c.tag.endswith("data")), None)
        if data_el is None:
            continue
        text = data_el.text or ""
        if data_el.get("format") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8", errors="replace")
            except ValueError:
                continue
        codes.append(Code(sym.get("type", "Code"), text))
    return codes


def _decode_zbar(img: QImage) -> list[Code]:
    exe = shutil.which("zbarimg")
    with tempfile.TemporaryDirectory(prefix="ksnapmark-qr-") as d:
        path = Path(d) / "in.png"
        img.save(str(path), "PNG")
        try:
            res = subprocess.run([exe, "--quiet", "--xml", str(path)], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise QrError(f"zbarimg: {exc}") from exc
    # Exit-Code 1 = nichts gefunden (kein Fehler); alles andere ≥ 2 schon
    if res.returncode not in (0, 1):
        raise QrError("zbarimg: " + res.stderr.decode(errors="replace").strip()[:200])
    return parse_zbar_xml(res.stdout.decode("utf-8", errors="replace"))


# --- OpenCV ---------------------------------------------------------------------------------

def _decode_opencv(img: QImage) -> list[Code]:
    import cv2
    import numpy as np

    rgb = img.convertToFormat(QImage.Format.Format_RGB888)
    arr = np.frombuffer(bytes(rgb.constBits())[: rgb.sizeInBytes()], dtype=np.uint8)
    arr = arr.reshape(rgb.height(), rgb.bytesPerLine())[:, : rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    detector = cv2.QRCodeDetector()
    found: list[Code] = []
    for scale in (1.0, 2.0, 0.5):
        frame = bgr if scale == 1.0 else cv2.resize(bgr, None, fx=scale, fy=scale,
                                                    interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
        try:
            ok, infos, _pts, _ = detector.detectAndDecodeMulti(frame)
        except cv2.error:
            ok, infos = False, []
        if ok:
            found += [Code("QR-Code", t) for t in infos if t]
        if found:
            break
    return found


# --- Inhalt aufbereiten ---------------------------------------------------------------------

_URL = re.compile(r"^https?://\S+$", re.I)


def is_url(text: str) -> bool:
    return bool(_URL.match(text.strip()))


def parse_wifi(text: str) -> dict[str, str] | None:
    """``WIFI:T:WPA;S:Netzname;P:Passwort;;`` -> {"Netzwerk": …, "Passwort": …, "Verschlüsselung": …}"""
    if not text.upper().startswith("WIFI:"):
        return None
    fields: dict[str, str] = {}
    for part in re.split(r"(?<!\\);", text[5:]):
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        fields[key.upper()] = re.sub(r"\\([\;,:\"])", r"\1", value)
    if "S" not in fields:
        return None
    return {tr("Network"): fields.get("S", ""), tr("Password"): fields.get("P", ""),
            tr("Security"): fields.get("T", "") or tr("none")}


def describe(code: Code) -> str:
    wifi = parse_wifi(code.data)
    if wifi:
        return "\n".join(f"{k}: {v}" for k, v in wifi.items())
    return code.data
