"""Attrappe fuer KWins Scripting-Schnittstelle: loadScript merkt sich die Datei, start() fuehrt sie mit node gegen ein
Fake-'workspace' aus und ruft ReceiveWindows zurueck - wie es KWin tun wuerde."""
import asyncio, json, re, subprocess, sys
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method
from dbus_next import Message

HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const mk = (o) => Object.assign({deleted:false, minimized:false, desktopWindow:false, dock:false, normalWindow:true, dialog:false, onAllDesktops:false, desktops:[{id:'d1'}], pid:1}, o);
const cur = {id:'d1'};
const wins = [
  mk({caption:'Plasma Desktop', desktopWindow:true, frameGeometry:{x:0,y:0,width:3840,height:1600}}),
  mk({caption:'Browser', resourceClass:'firefox', frameGeometry:{x:100,y:50,width:1200,height:800}, pid:11}),
  mk({caption:'Minimiert', minimized:true, frameGeometry:{x:0,y:0,width:500,height:500}}),
  mk({caption:'Panel', dock:true, frameGeometry:{x:0,y:1560,width:3840,height:40}}),
  mk({caption:'Anderer Desktop', desktops:[{id:'d2'}], frameGeometry:{x:0,y:0,width:500,height:500}}),
  mk({caption:'Tooltip', normalWindow:false, frameGeometry:{x:300,y:300,width:100,height:30}}),
  mk({caption:'Dialog', normalWindow:false, dialog:true, frameGeometry:{x:400,y:200,width:300,height:200}}),
  mk({caption:'Auf allen', onAllDesktops:true, desktops:[], resourceClass:'konsole', frameGeometry:{x:1400.4,y:60.6,width:900,height:700}}),
  mk({caption:'Leer', frameGeometry:{x:0,y:0,width:0,height:0}}),
];
const sent = [];
global.workspace = {stackingOrder: wins, currentDesktop: cur, activeWindow: wins[7]};
global.callDBus = (...a) => sent.push(a);
eval(src);
console.log(JSON.stringify(sent));
"""
HARNESS_PATH = "/tmp/ksnapmark_harness.js"
open(HARNESS_PATH, "w").write(HARNESS)

class Scripting(ServiceInterface):
    def __init__(self, bus):
        super().__init__("org.kde.kwin.Scripting"); self.bus = bus; self.loaded = {}
        self.log = []
    @method()
    def loadScript(self, path: 's', name: 's') -> 'i':
        self.loaded[name] = path; self.log.append(("load", name)); return 1
    @method()
    def start(self):
        for name, path in list(self.loaded.items()):
            src = open(path).read()
            service = re.search(r'SERVICE = "([^"]+)"', src).group(1)
            out = subprocess.run(["node", HARNESS_PATH, path], capture_output=True, text=True)
            if out.returncode != 0:
                print("NODE-FEHLER", out.stderr, file=sys.stderr, flush=True); continue
            args = json.loads(out.stdout)[0]
            asyncio.get_event_loop().create_task(self.callback(args))
    async def callback(self, args):
        service, path, iface, member, payload = args
        await self.bus.call(Message(destination=service, path=path, interface=iface, member=member, signature="s", body=[payload]))
    @method()
    def unloadScript(self, name: 's') -> 'b':
        self.log.append(("unload", name)); self.loaded.pop(name, None); return True

async def main():
    bus = await MessageBus().connect()
    bus.export("/Scripting", Scripting(bus))
    await bus.request_name("org.kde.KWin")
    print("READY", flush=True)
    await asyncio.get_event_loop().create_future()
asyncio.run(main())
