import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
app = QApplication(["t"])
from ksnapmark import qr
import qrcode
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
SCR = os.path.dirname(os.path.abspath(__file__))

def make(text, box=6):
    q = qrcode.QRCode(box_size=box, border=3); q.add_data(text); q.make(fit=True)
    pil = q.make_image(fill_color="black", back_color="white").convert("RGB")
    path = f"{SCR}/qr_{abs(hash(text)) % 10000}.png"; pil.save(path); return QImage(path)

def screenshot(*codes):
    """Screenshot-Attrappe: weisser Hintergrund mit Codes und Text"""
    img = QImage(900, 420, QImage.Format.Format_RGB32); img.fill(QColor("#eeeeee"))
    p = QPainter(img); x = 20
    for c in codes:
        p.drawImage(x, 30, c); x += c.width() + 40
    p.fillRect(20, 380, 300, 20, QColor("#999999")); p.end(); return img

check("Backend erkannt", qr.backend() in ("zbar", "opencv"), str(qr.backend()))
# The OpenCV checks must not depend on a system zbarimg (CI has one installed): hide it from PATH.
_real_path = os.environ["PATH"]
os.environ["PATH"] = tempfile.mkdtemp()
check("OpenCV-Backend ohne zbarimg", qr.backend() == "opencv", str(qr.backend()))
one = screenshot(make("https://example.com/angebot?id=42"))
codes = qr.decode(one)
check("OpenCV: URL gelesen", [c.data for c in codes] == ["https://example.com/angebot?id=42"], str([c.data for c in codes]))
two = screenshot(make("Hallo KSnapMark"), make("WIFI:T:WPA;S:Heimnetz;P:geheim;;"))
codes = qr.decode(two)
check("OpenCV: zwei Codes im Bild", {c.data for c in codes} == {"Hallo KSnapMark", "WIFI:T:WPA;S:Heimnetz;P:geheim;;"}, str([c.data for c in codes]))
check("kein Code -> leere Liste", qr.decode(screenshot()) == [])

# zbar-Pfad mit Attrappen-Programm
os.environ["PATH"] = _real_path
import textwrap
d = tempfile.mkdtemp(); fake = os.path.join(d, "zbarimg")
open(fake, "w").write(textwrap.dedent('''#!/usr/bin/env bash
cat <<'XML'
<barcodes xmlns='http://zbar.sourceforge.net/2008/barcode'><source href='x.png'><index num='0'>
<symbol type='QR-Code' quality='1'><data><![CDATA[https://a.example/x?y=1&z=2]]></data></symbol>
<symbol type='EAN-13' quality='1'><data><![CDATA[4006381333931]]></data></symbol>
<symbol type='QR-Code' quality='1'><data format='base64'>SGFsbG8gV2VsdA==</data></symbol>
<symbol type='QR-Code' quality='1'><data><![CDATA[https://a.example/x?y=1&z=2]]></data></symbol>
</index></source></barcodes>
XML
exit 0
'''))
os.chmod(fake, 0o755)
old = os.environ["PATH"]; os.environ["PATH"] = d + ":" + old
check("zbar bevorzugt", qr.backend() == "zbar")
codes = qr.decode(one)
check("zbar: XML geparst, Duplikate entfernt", [(c.kind, c.data) for c in codes] == [("QR-Code", "https://a.example/x?y=1&z=2"), ("EAN-13", "4006381333931"), ("QR-Code", "Hallo Welt")], str([(c.kind, c.data) for c in codes]))
open(fake, "w").write("#!/usr/bin/env bash\nexit 1\n")
check("zbar Exit 1 = nichts gefunden", qr.decode(one) == [])
open(fake, "w").write("#!/usr/bin/env bash\necho kaputt >&2\nexit 3\n")
try: qr.decode(one); check("zbar Fehler wird gemeldet", False)
except qr.QrError as e: check("zbar Fehler wird gemeldet", "kaputt" in str(e))
os.environ["PATH"] = old

check("URL erkannt", qr.is_url("https://x.de/a") and not qr.is_url("javascript:alert(1)") and not qr.is_url("hallo https://x.de"))
w = qr.parse_wifi("WIFI:T:WPA;S:Mein\;Netz;P:pa\\:ss;;")
check("WLAN-Daten zerlegt (mit Escapes)", w == {"Netzwerk": "Mein;Netz", "Passwort": "pa:ss", "Verschlüsselung": "WPA"}, str(w))
check("kein WLAN", qr.parse_wifi("https://x.de") is None)

# Dialog + Editor
from ksnapmark.dialogs import QrDialog
dlg = QrDialog(codes[:1] + [qr.Code("QR-Code", "WIFI:T:WPA;S:Heimnetz;P:geheim;;")]); dlg.show(); app.processEvents()
dlg.grab().save(f"{SCR}/qr_dialog.png")
from PySide6.QtWidgets import QPushButton
labels = [b.text() for b in dlg.findChildren(QPushButton)]
check("Dialog: Link oeffnen + Passwort kopieren vorhanden", "Link öffnen" in labels and "Passwort kopieren" in labels, str(labels))
from ksnapmark.app import Context
import ksnapmark.editor as ed, time
shown = []
ed.QrDialog = lambda c, parent=None: type("D", (), {"exec": lambda self: shown.append(c)})()
w = ed.EditorWindow(one, 1.0, Context(), record=False); w.show()
w.read_qr()
end = time.monotonic() + 30
while time.monotonic() < end and not shown: app.processEvents(); time.sleep(0.05)
check("Editor: QR lesen oeffnet Ergebnisdialog", shown and shown[0][0].data == "https://example.com/angebot?id=42")
w._dirty = False
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
