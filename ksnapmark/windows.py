"""Fensterliste von KWin (KDE Plasma, Wayland) – damit die Auswahl auf Fenstern einrasten kann.

Wayland erlaubt Programmen nicht, Fenster anderer Programme abzufragen. KWin kann es aber per
Skript: KSnapMark lädt kurz ein winziges KWin-Skript, das die sichtbaren Fenster samt Position
per D-Bus an KSnapMark zurückmeldet, und entlädt es sofort wieder. Ohne KWin (oder wenn etwas
schiefgeht) gibt es einfach keine Fensterliste, und die Auswahl funktioniert wie gewohnt.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import ClassInfo, QEventLoop, QObject, QRect, QTimer, Slot

try:
    from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
    HAVE_DBUS = True
except Exception:  # noqa: BLE001
    HAVE_DBUS = False

from . import dbus_capture

IFACE = "org.ksnapmark.Windows"
OBJ_PATH = "/Windows"
KWIN_SCRIPTING = ("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")

SCRIPT = r"""
(function () {
  var SERVICE = "__SERVICE__", PATH = "__PATH__", IFACE = "__IFACE__";
  function safe(f, d) { try { var v = f(); return (v === undefined || v === null) ? d : v; } catch (e) { return d; } }
  var list = safe(function () { return workspace.stackingOrder; }, null);
  if (!list) list = safe(function () { return workspace.windowList(); }, null);
  if (!list) list = safe(function () { return workspace.clientList(); }, []);
  var cur = safe(function () { return workspace.currentDesktop; }, null);
  var active = safe(function () { return workspace.activeWindow; }, null);
  var out = [];
  for (var i = 0; i < list.length; i++) {
    var w = list[i];
    if (!w) continue;
    if (safe(function () { return w.deleted; }, false)) continue;
    if (safe(function () { return w.minimized; }, false)) continue;
    if (safe(function () { return w.desktopWindow; }, false)) continue;
    if (safe(function () { return w.dock; }, false)) continue;
    var normal = safe(function () { return w.normalWindow; }, null);
    var dialog = safe(function () { return w.dialog; }, null);
    if (normal === false && dialog !== true) continue;          // Popups, Tooltips, Benachrichtigungen …
    var onAll = safe(function () { return w.onAllDesktops; }, false);
    var desks = safe(function () { return w.desktops; }, []);
    var here = onAll || desks.length === 0 || cur === null;
    for (var k = 0; !here && k < desks.length; k++) {
      if (desks[k] === cur || (desks[k] && cur && desks[k].id === cur.id)) here = true;
    }
    if (!here) continue;
    var g = safe(function () { return w.frameGeometry; }, null);
    if (!g || !(g.width > 0) || !(g.height > 0)) continue;
    out.push({
      title: String(safe(function () { return w.caption; }, "")),
      app: String(safe(function () { return w.resourceClass; }, "")),
      pid: safe(function () { return w.pid; }, 0),
      x: Math.round(g.x), y: Math.round(g.y), w: Math.round(g.width), h: Math.round(g.height),
      active: active !== null && w === active
    });
  }
  callDBus(SERVICE, PATH, IFACE, "ReceiveWindows", JSON.stringify({windows: out}));
})();
"""


@dataclass
class Win:
    title: str
    app: str
    rect: QRect   # globale logische Koordinaten
    pid: int = 0
    active: bool = False


def parse_windows(payload: str) -> list[Win]:
    """JSON des KWin-Skripts -> Fenster (unten -> oben, wie im Stapel)."""
    try:
        data = json.loads(payload)
        items = data["windows"]
    except (ValueError, KeyError, TypeError):
        return []
    wins: list[Win] = []
    for it in items:
        try:
            rect = QRect(int(it["x"]), int(it["y"]), int(it["w"]), int(it["h"]))
        except (KeyError, TypeError, ValueError):
            continue
        if rect.width() < 20 or rect.height() < 20:
            continue
        wins.append(Win(str(it.get("title", "")), str(it.get("app", "")), rect,
                        int(it.get("pid") or 0), bool(it.get("active"))))
    return wins


@ClassInfo(**{"D-Bus Interface": IFACE})
class _Receiver(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.payload: str | None = None
        self.loop: QEventLoop | None = None

    @Slot(str)
    def ReceiveWindows(self, payload: str) -> None:  # noqa: N802 - D-Bus-Methodenname
        self.payload = payload
        if self.loop is not None:
            self.loop.quit()


_receiver: _Receiver | None = None
_service = ""


def available() -> bool:
    return HAVE_DBUS and dbus_capture.kwin_available() and dbus_capture._service_known(KWIN_SCRIPTING[0])


def _ensure_service() -> bool:
    global _receiver, _service
    if _receiver is not None:
        return True
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    name = f"org.ksnapmark.p{os.getpid()}"
    if not bus.registerService(name):
        return False
    recv = _Receiver()
    if not bus.registerObject(OBJ_PATH, recv, QDBusConnection.RegisterOption.ExportAllSlots):
        bus.unregisterService(name)
        return False
    _receiver, _service = recv, name
    return True


def _call(member: str, *args, timeout_ms: int = 1500):
    msg = QDBusMessage.createMethodCall(*KWIN_SCRIPTING, member)
    msg.setArguments(list(args))
    return QDBusConnection.sessionBus().call(msg, QDBus.CallMode.Block, timeout_ms)


def query_windows(timeout_ms: int = 1200) -> list[Win] | None:
    """Sichtbare Fenster (unten -> oben) oder ``None``, wenn KWin sie nicht liefern konnte."""
    if not available() or not _ensure_service():
        return None
    recv = _receiver
    assert recv is not None
    plugin = "ksnapmark-windows-" + uuid.uuid4().hex[:8]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    fd, path = tempfile.mkstemp(prefix=plugin + "-", suffix=".js",
                                dir=runtime if runtime and os.path.isdir(runtime) else None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(SCRIPT.replace("__SERVICE__", _service).replace("__PATH__", OBJ_PATH)
                    .replace("__IFACE__", IFACE))
        recv.payload = None
        loop = QEventLoop()
        recv.loop = loop
        reply = _call("loadScript", path, plugin)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return None
        # Plasma 6 liefert bei loadScript teils 0, obwohl es klappt: maßgeblich ist die Rückmeldung des Skripts
        _call("start")
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        if recv.payload is None:
            loop.exec()
        timer.stop()
        return parse_windows(recv.payload) if recv.payload is not None else None
    finally:
        recv.loop = None
        try:
            _call("unloadScript", plugin, timeout_ms=500)
        except Exception:  # noqa: BLE001
            pass
        Path(path).unlink(missing_ok=True)
