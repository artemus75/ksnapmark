"""Bildschirmaufnahme für X11 und Wayland (KDE, GNOME, wlroots).

Reihenfolge der Verfahren (je nach Desktop angepasst, das erste funktionierende gewinnt):

1. ``kwin``   – KDE: KWin-D-Bus, pro Monitor in nativer Auflösung, ohne Zusatzprogramm
2. ``portal`` – xdg-desktop-portal, ohne Zusatzprogramm
3. Hilfsprogramme: spectacle, grim, gnome-screenshot, maim, scrot, import
"""

from __future__ import annotations

from .i18n import tr

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QImageReader, QScreen

from . import dbus_capture

# Gesamtbilder mehrerer Monitore sind schnell > 256 MB (Qt-Standardgrenze) – Grenze anheben.
os.environ.setdefault("QT_IMAGEIO_MAXALLOC", "4096")
try:
    QImageReader.setAllocationLimit(0)
except Exception:  # noqa: BLE001 - ältere Qt-Versionen kennen die Funktion nicht
    pass

MISSING_HINT = (
    tr("No way to capture the screen was found.\nNeither the KWin/portal interface nor a helper program is reachable.\nWayland (Sway/Hyprland etc.): sudo pacman -S grim\nKDE Plasma: sudo pacman -S spectacle\nGNOME: sudo pacman -S gnome-screenshot\nX11: sudo pacman -S maim")
)

# Meldungen der zuletzt versuchten Verfahren (für Fehlerdialog und --doctor)
LAST_ERRORS: list[str] = []
# Verfahren, das die letzte Aufnahme geliefert hat
LAST_BACKEND = ""


def _desktop() -> str:
    return (os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" +
            os.environ.get("XDG_SESSION_DESKTOP", "")).lower()


# --- Hilfsprogramme ---------------------------------------------------------------------

def _stdout_png(cmd: list[str]) -> QImage | None:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        LAST_ERRORS.append(f"{cmd[0]}: {exc}")
        return None
    img = QImage.fromData(res.stdout) if res.stdout else QImage()
    if img.isNull():
        err = res.stderr.decode(errors="replace").strip()[:200]
        LAST_ERRORS.append(f"{cmd[0]}: exit code {res.returncode}, no image data. {err}")
        return None
    return img


def _wait_for_image(path: Path, timeout: float = 40.0) -> QImage | None:
    """Wartet, bis die Datei fertig geschrieben ist (Spectacle kehrt teils vorher zurück)."""
    end = time.monotonic() + timeout
    last_size = -1
    stable_since: float | None = None
    load_failures = 0
    while time.monotonic() < end:
        size = path.stat().st_size if path.exists() else 0
        if size > 0 and size == last_size:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 0.4:
                img = QImage(str(path))
                if not img.isNull():
                    return img
                load_failures += 1
                if load_failures >= 2:
                    return None
                stable_since = None
        else:
            stable_since = None
        last_size = size
        time.sleep(0.2)
    return None


def _file_png(builders) -> QImage | None:
    for build in builders:
        with tempfile.TemporaryDirectory(prefix="ksnapmark-cap-") as d:
            path = Path(d) / "shot.png"
            cmd = build(str(path))
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=60)
            except Exception as exc:  # noqa: BLE001
                LAST_ERRORS.append(f"{cmd[0]}: {exc}")
                continue
            # Spectacle kehrt mit Code 0 vor dem Schreiben zurück -> lange warten; bei Fehlercode kaum
            img = _wait_for_image(path, timeout=40.0 if res.returncode == 0 else 2.0)
            if img is not None:
                return img
            err = res.stderr.decode(errors="replace").strip()[:200]
            LAST_ERRORS.append(f"{' '.join(cmd[:-1])}: exit code {res.returncode}, "
                               f"no readable file. {err}")
    return None


def include_cursor() -> bool:
    """Setting "include_cursor": capture the mouse pointer, too (default: no)."""
    from . import config

    try:
        return bool(config.load().include_cursor)
    except Exception:  # noqa: BLE001 - a broken config must never stop a capture
        return False


def _flag(option: str) -> list[str]:
    """The tool's "include the pointer" option, if the user asked for the pointer."""
    return [option] if include_cursor() else []


def _spectacle() -> QImage | None:
    variants = [lambda f: ["spectacle", "-b", "-n", *_flag("-p"), "-f", "-o", f]]  # alle Monitore
    if len(QGuiApplication.screens()) == 1:
        variants.append(lambda f: ["spectacle", "-b", "-n", *_flag("-p"), "-m", "-o", f])
    return _file_png(variants)


def _portal() -> QImage | None:
    try:
        return dbus_capture.portal_screenshot()
    except dbus_capture.CaptureError as exc:
        LAST_ERRORS.append(str(exc))
        return None


# Verfahren, die den gesamten Desktop als ein Bild liefern
_DESKTOP_BACKENDS = {
    "portal": _portal,
    "spectacle": _spectacle,
    "grim": lambda: _stdout_png(["grim", *_flag("-c"), "-t", "png", "-l", "0", "-"]),
    "gnome-screenshot": lambda: _file_png([lambda f: ["gnome-screenshot", *_flag("-p"), "-f", f]]),
    "maim": lambda: _stdout_png(["maim"]),
    "scrot": lambda: _file_png([lambda f: ["scrot", *_flag("-p"), "-o", f]]),
    "import": lambda: _file_png([lambda f: ["import", "-window", "root", f]]),
}
ALL_BACKENDS = ["kwin"] + list(_DESKTOP_BACKENDS)


def is_available(name: str) -> bool:
    if name == "kwin":
        return dbus_capture.kwin_available()
    if name == "portal":
        return dbus_capture.portal_available()
    return shutil.which(name) is not None


def backend_order(preferred: str = "auto") -> list[str]:
    desk = _desktop()
    if "kde" in desk:
        base = ["kwin", "spectacle", "grim", "portal"]
    elif "gnome" in desk:
        base = ["gnome-screenshot", "portal", "grim"]
    else:
        base = ["grim", "portal", "spectacle", "gnome-screenshot"]
    order = base + [b for b in ALL_BACKENDS if b not in base]
    if preferred in ALL_BACKENDS:
        order = [preferred] + [b for b in order if b != preferred]
    return order


# Nur unter X11 sinnvoll: in einer Wayland-Sitzung sehen sie höchstens XWayland-Fenster
X11_ONLY = ("maim", "scrot", "import")


def available_backends(preferred: str = "auto") -> list[str]:
    wayland = os.environ.get("WAYLAND_DISPLAY") is not None
    return [b for b in backend_order(preferred)
            if is_available(b) and not (wayland and b in X11_ONLY and b != preferred)]


# --- Prüfungen -------------------------------------------------------------------------

def _looks_blank(img: QImage) -> bool:
    """Nur komplett schwarz/transparent gilt als leer (typisch für fehlgeschlagene Wayland-Grabs)."""
    if img.isNull():
        return True
    w, h = img.width(), img.height()
    first = img.pixel(0, 0)
    if (first & 0x00FFFFFF) != 0 and (first >> 24) != 0:
        return False
    for iy in range(1, 17):
        for ix in range(1, 17):
            if img.pixel(ix * w // 18, iy * h // 18) != first:
                return False
    return True


def _covers_all_screens(img: QImage) -> bool:
    """Passt das Bild zum Gesamt-Desktop? (Ein Einzelmonitor-Bild darf nicht verteilt werden.)"""
    screens = QGuiApplication.screens()
    if not screens:
        return True
    virt = screens[0].virtualGeometry()
    if virt.width() <= 0 or virt.height() <= 0:
        return True
    rw = img.width() / virt.width()
    rh = img.height() / virt.height()
    return rw >= 0.98 and abs(rw - rh) / rw <= 0.03


def _desktop_image(name: str) -> QImage | None:
    """Gesamtbild eines Verfahrens holen und prüfen."""
    img = _DESKTOP_BACKENDS[name]()
    if img is None:
        return None
    if _looks_blank(img):
        LAST_ERRORS.append(f"{name}: returned only a black image")
        return None
    if not _covers_all_screens(img):
        virt = QGuiApplication.screens()[0].virtualGeometry()
        LAST_ERRORS.append(
            f"{name}: image {img.width()}x{img.height()} does not match the desktop "
            f"({virt.width()}x{virt.height()} logical) – probably only one monitor")
        return None
    return img


def _kwin_screens(screens: list[QScreen]) -> list[tuple[QScreen, QImage]] | None:
    """Jeden Monitor einzeln über KWin aufnehmen; bei einem Fehler Abbruch (-> nächstes Verfahren)."""
    result: list[tuple[QScreen, QImage]] = []
    cursor = include_cursor()
    for screen in screens:
        try:
            img = dbus_capture.kwin_capture_screen(screen.name(), include_cursor=cursor)
        except dbus_capture.CaptureError as exc:
            LAST_ERRORS.append(f"kwin ({screen.name()}): {exc}")
            return None
        geo = screen.geometry()
        ratio = img.width() / max(1, geo.width())
        if not 0.9 <= ratio <= 4.5:
            LAST_ERRORS.append(f"kwin ({screen.name()}): image size {img.width()}x{img.height()} "
                               f"does not match the monitor ({geo.width()}x{geo.height()})")
            return None
        if _looks_blank(img):
            LAST_ERRORS.append(f"kwin ({screen.name()}): returned only a black image")
            return None
        img.setDevicePixelRatio(ratio)
        result.append((screen, img))
    return result


# --- Zuordnung Gesamtbild -> Monitor ------------------------------------------------------

def _crop_to_screen(full: QImage, screen: QScreen) -> QImage:
    """Schneidet den Monitor aus dem Gesamtbild und bringt ihn auf seine echte Auflösung."""
    geo = screen.geometry()
    img = full
    if len(QGuiApplication.screens()) > 1:
        virt = screen.virtualGeometry()
        ratio = full.width() / virt.width()
        rect = QRect(round((geo.x() - virt.x()) * ratio), round((geo.y() - virt.y()) * ratio),
                     round(geo.width() * ratio), round(geo.height() * ratio))
        img = full.copy(rect.intersected(full.rect()))
        # Gesamtbild liegt in der höchsten Skalierung vor; Monitore mit kleinerer Skalierung
        # (z. B. 1x neben einem 2x-Display) auf ihre eigene native Größe zurückrechnen.
        native = float(screen.devicePixelRatio())
        target_w, target_h = round(geo.width() * native), round(geo.height() * native)
        if target_w > 0 and img.width() > target_w * 1.02:
            img = img.scaled(target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    img = QImage(img)
    img.setDevicePixelRatio(img.width() / geo.width())
    return img


# --- Öffentliche Funktionen -------------------------------------------------------------------

def capture_screens(screens: list[QScreen], preferred: str = "auto") -> list[tuple[QScreen, QImage]]:
    """Nimmt die Monitore auf. Gibt (Monitor, Bild) zurück; leer, wenn alles fehlschlug."""
    global LAST_BACKEND
    LAST_ERRORS.clear()
    LAST_BACKEND = ""
    result: list[tuple[QScreen, QImage]] = []

    test = os.environ.get("KSNAPMARK_TEST_IMAGE")  # nur für Entwicklung/Tests
    if test:
        full = QImage(test)
        if full.isNull():
            return []
        LAST_BACKEND = "test"
        return [(s, _crop_to_screen(full, s)) for s in screens]

    remaining = list(screens)
    if QGuiApplication.platformName() == "xcb":  # X11: Qt kann selbst grabben
        for screen in list(remaining):
            pm = screen.grabWindow(0)
            if pm.isNull():
                continue
            grabbed = pm.toImage()
            if _looks_blank(grabbed):
                continue
            grabbed.setDevicePixelRatio(grabbed.width() / screen.geometry().width())
            result.append((screen, grabbed))
            remaining.remove(screen)
        if not remaining:
            LAST_BACKEND = "qt-x11"
            return result

    usable = available_backends(preferred)
    for name in backend_order(preferred):
        if not remaining:
            break
        if name not in usable:
            continue
        if name == "kwin":
            got = _kwin_screens(remaining)
            if got is not None:
                result += got
                remaining = []
                LAST_BACKEND = "kwin"
            continue
        full = _desktop_image(name)
        if full is None:
            continue
        result += [(s, _crop_to_screen(full, s)) for s in remaining]
        remaining = []
        LAST_BACKEND = name
    return result if not remaining else []


def capture_screen(screen: QScreen, preferred: str = "auto") -> QImage | None:
    shots = capture_screens([screen], preferred)
    return shots[0][1] if shots else None


def test_backend(name: str) -> tuple[bool, float, str]:
    """Ein Verfahren einzeln ausprobieren (für ``ksnapmark --doctor``)."""
    LAST_ERRORS.clear()
    start = time.monotonic()
    screens = QGuiApplication.screens()
    if name == "kwin":
        got = _kwin_screens(screens)
        ok = got is not None
        detail = (", ".join(f"{s.name()} {i.width()}x{i.height()}" for s, i in got)
                  if got else "; ".join(LAST_ERRORS))
    else:
        img = _desktop_image(name)
        ok = img is not None
        detail = f"{img.width()}x{img.height()}" if img else "; ".join(LAST_ERRORS)
    return ok, time.monotonic() - start, detail


def failure_message() -> str:
    """Text für den Fehlerdialog: fehlende Werkzeuge oder konkrete Fehler der vorhandenen."""
    if not available_backends():
        return MISSING_HINT
    details = "\n".join(f"• {e}" for e in LAST_ERRORS) or "• no details available"
    return (tr("The capture failed.\n\nMethods tried:\n") + details +
            tr("\n\nTip: run 'ksnapmark --doctor' in a terminal."))
