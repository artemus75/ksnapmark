"""Eingebaute Aufnahme über D-Bus: KWin (pro Monitor) und xdg-desktop-portal.

Beides braucht keine Zusatzprogramme wie grim oder Spectacle.

- KWin (``org.kde.KWin.ScreenShot2``): KDE Plasma, kein Dialog, native Auflösung je Monitor.
  KWin gibt die Schnittstelle nur freigegebenen Programmen; sonst kommt ein Fehler und
  KSnapMark weicht auf das nächste Verfahren aus.
- Portal (``org.freedesktop.portal.Screenshot``): funktioniert auf KDE, GNOME und wlroots,
  liefert das Bild des gesamten Desktops. Je nach Desktop erscheint einmal eine Rückfrage.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Slot, SLOT
from PySide6.QtGui import QImage

try:  # QtDBus fehlt in manchen Minimal-Installationen
    from PySide6.QtDBus import (QDBus, QDBusConnection, QDBusError, QDBusMessage,
                                QDBusUnixFileDescriptor)
    HAVE_DBUS = True
except Exception:  # noqa: BLE001
    HAVE_DBUS = False

KWIN = ("org.kde.KWin", "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2")
PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")


class CaptureError(RuntimeError):
    pass


def _bus():
    if not HAVE_DBUS:
        raise CaptureError("QtDBus is not available.")
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise CaptureError("No connection to the D-Bus session bus.")
    return bus


def _service_known(name: str) -> bool:
    if not HAVE_DBUS:
        return False
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    iface = bus.interface()
    if iface is None:
        return False
    if iface.isServiceRegistered(name).value():
        return True
    activatable = iface.activatableServiceNames().value()
    return name in (activatable or [])


def kwin_available() -> bool:
    return os.environ.get("WAYLAND_DISPLAY") is not None and _service_known(KWIN[0])


def portal_available() -> bool:
    return _service_known(PORTAL[0])


def _unwrap(value):
    """QtDBus liefert Werte teils als QDBusVariant."""
    if hasattr(value, "variant"):
        value = value.variant()
    return value


# --- KWin ---------------------------------------------------------------------------

class _KWinReply(QObject):
    """Qt wandelt die a{sv}-Antwort für Slots selbst um (Direktzugriff auf QDBusArgument geht in Python nicht)."""

    def __init__(self, loop: QEventLoop):
        super().__init__()
        self.loop = loop
        self.result: dict | None = None
        self.error: str | None = None

    @Slot("QVariantMap")
    def on_ok(self, res) -> None:
        self.result = {str(k): _unwrap(v) for k, v in dict(res).items()}
        self.loop.quit()

    @Slot(QDBusError, QDBusMessage)
    def on_err(self, err, _msg) -> None:
        self.error = f"{err.name()} {err.message()}".strip()
        self.loop.quit()


def kwin_capture_screen(name: str, timeout_ms: int = 20000, include_cursor: bool = False) -> QImage:
    """Einen Monitor in nativer Auflösung aufnehmen (rohe Pixel über eine Pipe)."""
    bus = _bus()
    read_fd, write_fd = os.pipe()
    chunks: list[bytes] = []

    def drain() -> None:
        try:
            while True:
                data = os.read(read_fd, 1 << 20)
                if not data:
                    break
                chunks.append(data)
        finally:
            os.close(read_fd)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    loop = QEventLoop()
    receiver = _KWinReply(loop)
    msg = QDBusMessage.createMethodCall(*KWIN, "CaptureScreen")
    fd_obj = QDBusUnixFileDescriptor(write_fd)  # dupliziert den Deskriptor
    os.close(write_fd)
    msg.setArguments([name, {"native-resolution": True, "include-cursor": bool(include_cursor)}, fd_obj])
    sent = bus.callWithCallback(msg, receiver, SLOT("on_ok(QVariantMap)"),
                                SLOT("on_err(QDBusError,QDBusMessage)"), timeout_ms)
    if sent:
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms + 2000)
        if receiver.result is None and receiver.error is None:
            loop.exec()
        timer.stop()
    del msg, fd_obj  # letzte Kopie des Schreibendes schließen -> Leser sieht EOF
    reader.join(timeout=timeout_ms / 1000)

    if not sent:
        raise CaptureError("KWin: call could not be sent")
    if receiver.error:
        raise CaptureError(f"KWin: {receiver.error}")
    meta = receiver.result
    if meta is None:
        raise CaptureError("KWin: no reply (timeout)")
    try:
        width, height = int(meta["width"]), int(meta["height"])
        stride, fmt = int(meta["stride"]), int(meta["format"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CaptureError(f"KWin: reply without image metadata ({sorted(meta)})") from exc
    raw = b"".join(chunks)
    if len(raw) < stride * height:
        raise CaptureError(f"KWin: image data incomplete ({len(raw)} of {stride * height} Bytes)")
    img = QImage(raw, width, height, stride, QImage.Format(fmt)).convertToFormat(
        QImage.Format.Format_RGB32)
    if img.isNull():
        raise CaptureError("KWin: image could not be read")
    return img


def QDBusMessage_block():
    return QDBus.CallMode.Block


# --- Portal -------------------------------------------------------------------------

class _ResponseReceiver(QObject):
    def __init__(self, loop: QEventLoop):
        super().__init__()
        self.loop = loop
        self.code: int | None = None
        self.results: dict = {}

    @Slot("uint", "QVariantMap")
    def on_response(self, code, results) -> None:
        self.code = int(code)
        self.results = {str(k): _unwrap(v) for k, v in dict(results).items()}
        self.loop.quit()


def portal_screenshot(timeout_s: int = 90) -> QImage:
    """Gesamten Desktop über das Portal aufnehmen."""
    bus = _bus()
    token = "ksnapmark_" + uuid.uuid4().hex[:12]
    sender = bus.baseService().lstrip(":").replace(".", "_")
    request_path = f"{PORTAL[1]}/request/{sender}/{token}"

    loop = QEventLoop()
    receiver = _ResponseReceiver(loop)
    connected = bus.connect(PORTAL[0], request_path, "org.freedesktop.portal.Request", "Response",
                            receiver, SLOT("on_response(uint,QVariantMap)"))
    if not connected:
        raise CaptureError("Portal: could not subscribe to the response signal")

    msg = QDBusMessage.createMethodCall(PORTAL[0], PORTAL[1], "org.freedesktop.portal.Screenshot",
                                        "Screenshot")
    msg.setArguments(["", {"handle_token": token, "interactive": False, "modal": False}])
    reply = bus.call(msg, QDBusMessage_block(), 10000)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        raise CaptureError(f"Portal: {reply.errorName()} {reply.errorMessage()}".strip())

    QTimer.singleShot(timeout_s * 1000, loop.quit)
    if receiver.code is None:
        loop.exec()
    if receiver.code is None:
        raise CaptureError("Portal: no reply (timeout)")
    if receiver.code != 0:
        raise CaptureError("Portal: capture denied or cancelled")
    uri = str(receiver.results.get("uri", ""))
    path = QUrl(uri).toLocalFile()
    if not path:
        raise CaptureError(f"Portal: no file in the reply ({uri!r})")
    img = QImage(path)
    _cleanup_temp(path)
    if img.isNull():
        raise CaptureError(f"Portal: image not readable ({path})")
    return img


def _cleanup_temp(path: str) -> None:
    """Nur Dateien in temporären Ordnern löschen – nie etwas aus dem Bilder-Ordner."""
    p = Path(path)
    safe_roots = [Path("/tmp"), Path(os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")),
                  Path.home() / ".cache"]
    try:
        resolved = p.resolve()
        if any(str(resolved).startswith(str(root.resolve()) + os.sep) for root in safe_roots):
            resolved.unlink()
    except OSError:
        pass
