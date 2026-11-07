"""Verständigung zwischen Tastenkürzel-Aufruf und dem im Hintergrund laufenden KSnapMark.

Der Client-Teil nutzt nur die Standardbibliothek (kein Qt-Import), damit ein Aufruf per
Tastenkürzel den schon laufenden Hintergrundprozess in wenigen Millisekunden erreicht.
"""

from __future__ import annotations

from .i18n import tr

import json
import os
import socket
import tempfile
from dataclasses import asdict, dataclass, fields


@dataclass
class Job:
    action: str = "capture"   # capture | ideas | open | ping | quit
    mode: str = "edit"        # edit | ocr | copy | save
    full: bool = False
    screen: str | None = None
    delay: float = 0.0
    file: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def socket_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base):
        return os.path.join(base, "ksnapmark.sock")
    return os.path.join(tempfile.gettempdir(), f"ksnapmark-{os.getuid()}.sock")


def send(job: Job, timeout: float = 3.0) -> dict | None:
    """Auftrag an den Hintergrundprozess schicken.

    ``None``: es läuft keiner. Sonst dessen Antwort ``{"ok": bool, ...}``.
    """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(socket_path())
        except (FileNotFoundError, ConnectionRefusedError, NotADirectoryError):
            return None
        except socket.timeout:
            return {"ok": False, "error": tr("KSnapMark in the background does not respond (busy?)")}
        try:
            s.sendall(json.dumps(asdict(job)).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            return {"ok": False, "error": tr("KSnapMark in the background gives no answer")}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return json.loads(data) if data.strip() else {"ok": True}
        except ValueError:
            return {"ok": False, "error": tr("unintelligible reply")}
    finally:
        s.close()


def make_server(handler, parent=None):
    """Lokalen Server starten (Qt). ``handler(job)`` läuft im Qt-Hauptthread.

    Gibt das Server-Objekt zurück oder ``None``, wenn das Lauschen nicht möglich war.
    """
    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtNetwork import QLocalServer

    class _Server(QObject):
        def __init__(self) -> None:
            super().__init__(parent)
            self.server = QLocalServer(self)
            self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            self.server.newConnection.connect(self._accept)

        def listen(self) -> bool:
            path = socket_path()
            QLocalServer.removeServer(path)  # Überbleibsel eines abgestürzten Prozesses
            return self.server.listen(path)

        def error(self) -> str:
            return self.server.errorString()

        def _accept(self) -> None:
            while self.server.hasPendingConnections():
                sock = self.server.nextPendingConnection()
                sock.readyRead.connect(lambda s=sock: self._read(s))
                sock.disconnected.connect(sock.deleteLater)

        def _read(self, sock) -> None:
            if not sock.canReadLine():
                return
            line = bytes(sock.readLine()).decode(errors="replace")
            try:
                job = Job.from_dict(json.loads(line))
                reply = {"ok": True}
            except (ValueError, TypeError):
                job = None
                reply = {"ok": False, "error": tr("invalid job")}
            sock.write(json.dumps(reply).encode() + b"\n")
            sock.flush()
            sock.disconnectFromServer()
            if job is not None:  # erst nach der Antwort ausführen, der Aufrufer wartet nicht
                QTimer.singleShot(0, lambda j=job: handler(j))

    srv = _Server()
    if not srv.listen():
        return None
    return srv
