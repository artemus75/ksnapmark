"""Mock von KWin ScreenShot2 und xdg-desktop-portal Screenshot (nur für Tests)."""
import asyncio
import os
import threading

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from dbus_next import DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

DENY = os.environ.get("MOCK_KWIN_DENY") == "1"
COLORS = {"DP-4": (255, 0, 0), "eDP-1": (0, 255, 0)}


class KWin(ServiceInterface):
    def __init__(self):
        super().__init__("org.kde.KWin.ScreenShot2")

    @method()
    def CaptureScreen(self, name: "s", options: "a{sv}", pipe: "h") -> "a{sv}":
        if DENY:
            os.close(pipe)
            raise DBusError("org.kde.KWin.ScreenShot2.Error.NoAuthorized", "The process is not authorized")
        if not options.get("native-resolution", Variant("b", False)).value:
            os.close(pipe)
            raise DBusError("org.kde.KWin.ScreenShot2.Error.InvalidArgument", "native-resolution fehlt")
        w, h = (800, 400) if name == "eDP-1" else (400, 200)
        r, g, b = COLORS.get(name, (0, 0, 255))
        pixel = bytes([b, g, r, 255])  # ARGB32 little endian
        data = pixel * (w * h)

        def writer():
            with os.fdopen(pipe, "wb") as f:
                f.write(data)

        threading.Thread(target=writer).start()
        return {"type": Variant("s", "raw"), "width": Variant("u", w), "height": Variant("u", h),
                "stride": Variant("u", w * 4), "format": Variant("u", 6), "scale": Variant("d", 2.0 if name == "eDP-1" else 1.0)}


class Request(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.portal.Request")

    @signal()
    def Response(self, code: "u", results: "a{sv}") -> "ua{sv}":
        return [code, results]


class Portal(ServiceInterface):
    def __init__(self, bus):
        super().__init__("org.freedesktop.portal.Screenshot")
        self.bus = bus
        self.last_sender = None

    @method()
    def Screenshot(self, parent: "s", options: "a{sv}") -> "o":
        token = options["handle_token"].value
        sender = (self.last_sender or ":1.0").lstrip(":").replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        req = Request()
        self.bus.export(path, req)
        loop = asyncio.get_event_loop()

        async def respond():
            await asyncio.sleep(0.3)
            from PySide6.QtGui import QColor, QImage
            img = QImage(640, 360, QImage.Format.Format_RGB32)
            img.fill(QColor("#336699"))
            img.save("/tmp/mock_portal_shot.png")
            if os.environ.get("MOCK_PORTAL_DENY") == "1":
                req.Response(2, {})
            else:
                req.Response(0, {"uri": Variant("s", "file:///tmp/mock_portal_shot.png")})

        loop.create_task(respond())
        return path


async def main():
    kbus = await MessageBus(negotiate_unix_fd=True).connect()
    kbus.export("/org/kde/KWin/ScreenShot2", KWin())
    await kbus.request_name("org.kde.KWin")
    pbus = await MessageBus(negotiate_unix_fd=True).connect()
    portal = Portal(pbus)
    pbus.export("/org/freedesktop/portal/desktop", portal)

    def handler(msg):
        if msg.member == "Screenshot":
            portal.last_sender = msg.sender
    pbus.add_message_handler(handler)
    await pbus.request_name("org.freedesktop.portal.Desktop")
    print("READY", flush=True)
    await asyncio.get_event_loop().create_future()


asyncio.run(main())
