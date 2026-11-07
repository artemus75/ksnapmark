import os, sys, tempfile, time, subprocess
os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp(); os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(["t"])
from ksnapmark import recorder, system
from ksnapmark.app import Context, Controller
from ksnapmark.ipc import Job
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
work = Path(tempfile.mkdtemp())
# Test-Video erzeugen
vid = work / "test.mp4"
r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=15", "-c:v", "mpeg4", str(vid)], capture_output=True)
check("Test-Video erzeugt", vid.exists() and vid.stat().st_size > 0, r.stderr.decode()[:100])
check("ffmpeg erkannt", recorder.ffmpeg_available())
gif = recorder.convert_to_gif(vid, fps=10, width=320)
head = gif.read_bytes()[:6]
check("GIF erzeugt (GIF89a)", gif.suffix == ".gif" and head in (b"GIF89a", b"GIF87a"), f"{gif.name} {gif.stat().st_size} B")
probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(gif)], capture_output=True, text=True).stdout.strip()
check("Breite auf 320 begrenzt", probe.startswith("320,"), probe)
gif2 = recorder.convert_to_gif(vid, fps=10, width=2000)
check("zweites GIF ueberschreibt nichts", gif2 != gif and gif.exists() and gif2.exists(), gif2.name)
probe2 = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0", str(gif2)], capture_output=True, text=True).stdout.strip()
check("kleines Video wird nicht hochskaliert", probe2 == "640", probe2)
try: recorder.convert_to_gif(work / "gibtsnicht.mp4"); check("fehlende Datei -> Fehler", False)
except recorder.RecorderError as e: check("fehlende Datei -> Fehler", "nicht gefunden" in str(e))
bad = work / "kaputt.mp4"; bad.write_bytes(b"kein video")
try: recorder.convert_to_gif(bad); check("kaputtes Video -> Fehler", False)
except recorder.RecorderError as e: check("kaputtes Video -> Fehler, keine GIF-Reste", "ffmpeg" in str(e) and not bad.with_suffix(".gif").exists())

check("Befehl Bereich", recorder.record_command("region", Path("/x/a.webm")) == ["spectacle", "-b", "-R", "r", "-o", "/x/a.webm"])
check("Befehl Fenster/Bildschirm", recorder.record_command("window", Path("/x"))[3] == "w" and recorder.record_command("screen", Path("/x"))[3] == "s")
p1 = recorder.new_video_path(work, "mp4"); p1.write_bytes(b"x"); p2 = recorder.new_video_path(work, "mp4")
check("Dateiname ueberschreibt nichts / Format-Pruefung", p1 != p2 and recorder.new_video_path(work, "exe").suffix == ".webm")

# Attrappen-Spectacle
fake_dir = Path(tempfile.mkdtemp()); fake = fake_dir / "spectacle"
fake.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "--help" ]]; then echo "Options:"; echo "  -R, --record <mode>  Start recording"; exit 0; fi
out=""; while [[ $# -gt 0 ]]; do [[ "$1" == "-o" ]] && out="$2"; shift; done
sleep 1; cp {vid} "$out"; exit 0
""")
fake.chmod(0o755)
old = os.environ["PATH"]; os.environ["PATH"] = f"{fake_dir}:{old}"
check("Spectacle mit --record erkannt", recorder.spectacle_can_record())
recorder._support_cache = None
notes = []; system.notify = lambda t, m, *a, **k: notes.append(m)
warned = []; QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
ctx = Context(); ctx.cfg.record_dir = str(work / "videos"); ctx.cfg.record_format = "mp4"; ctx.cfg.record_gif = True
ctl = Controller(app, ctx, True)
ctl.handle(Job(action="record", mode="region"))
check("Zweiter Start waehrend der Aufnahme wird abgelehnt", (ctl.handle(Job(action="record", mode="screen")) or True) and any("bereits" in n for n in notes))
end = time.monotonic() + 40
while time.monotonic() < end and not any("GIF gespeichert" in n for n in notes):
    app.processEvents(); time.sleep(0.05)
vids = sorted((work / "videos").glob("*"))
check("Video + GIF im Zielordner", [v.suffix for v in vids] == [".gif", ".mp4"], str([v.name for v in vids]))
check("Benachrichtigungen: gestartet, gespeichert, GIF", any("gestartet" in n for n in notes) and any("Aufnahme gespeichert" in n for n in notes) and any("GIF gespeichert" in n for n in notes), str(notes))
check("Controller wieder frei", ctl._rec_proc is None)
# Spectacle ohne Aufnahme-Funktion
(fake_dir / "spectacle").write_text("#!/usr/bin/env bash\necho 'Options: -f fullscreen'\n"); recorder._support_cache = None
check("alte Spectacle-Version erkannt", not recorder.spectacle_can_record())
notes.clear(); ctl.handle(Job(action="record", mode="region"))
check("klare Fehlermeldung bei alter Version", bool(notes) and notes[-1].startswith("Für Bildschirmaufnahmen"), str(notes)[:80])
os.environ["PATH"] = old
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
