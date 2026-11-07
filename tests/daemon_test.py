import os, shutil, signal, subprocess, sys, tempfile, time
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
SCR = os.path.dirname(os.path.abspath(__file__))
home = tempfile.mkdtemp(prefix="ksnapmark-home-")
run = tempfile.mkdtemp(prefix="ksnapmark-run-")
os.chmod(run, 0o700)
env = dict(os.environ, HOME=home, XDG_RUNTIME_DIR=run, XDG_CONFIG_HOME=home + "/.config",
           XDG_DATA_HOME=home + "/.local/share", QT_QPA_PLATFORM="offscreen",
           KSNAPMARK_TEST_IMAGE=f"{SCR}/data/testbild.png", PYTHONPATH=os.path.dirname(SCR))
env.pop("WAYLAND_DISPLAY", None); env.pop("DISPLAY", None)
os.environ.update(XDG_RUNTIME_DIR=run)
from ksnapmark import ipc
res = []
def check(n, c, extra=""):
    res.append(c); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra else ""))
def cli(*a, timeout=60):
    t = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "ksnapmark", *a], env=env, capture_output=True, text=True, timeout=timeout)
    return p, time.monotonic() - t
def wait_up(sec=20):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        if ipc.send(ipc.Job(action="ping"), timeout=1) is not None: return True
        time.sleep(0.2)
    return False
def saved():
    d = home + "/Pictures/Screenshots"
    return sorted(os.listdir(d)) if os.path.isdir(d) else []

# Standalone: ein Prozess, endet selbst
p, dt = cli("--standalone", "--full", "--save")
check("standalone: beendet sich und speichert", p.returncode == 0 and len(saved()) == 1, f"rc={p.returncode} {p.stderr[-200:]}")
check("standalone: kein Hintergrundprozess uebrig", ipc.send(ipc.Job(action="ping"), timeout=1) is None)

# --quit ohne Daemon
p, _ = cli("--quit")
check("--quit ohne Daemon meldet es", p.returncode == 0 and "nicht" in p.stdout, p.stdout.strip())

# Daemon starten
d = subprocess.Popen([sys.executable, "-m", "ksnapmark", "--daemon"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
check("Daemon antwortet auf Ping", wait_up())
check("Daemon-Prozess laeuft", d.poll() is None)

# zweiter --daemon
p, _ = cli("--daemon")
check("zweiter --daemon: laeuft bereits", p.returncode == 0 and "bereits" in p.stdout, p.stdout.strip())

# Auftrag an Daemon
n0 = len(saved())
p, dt = cli("--full", "--save")
time.sleep(2.0)
check("Auftrag ueber Daemon speichert Bild", len(saved()) == n0 + 1, str(saved()))
check("Client ist schnell (<1,5 s)", dt < 1.5, f"{dt:.2f}s")
check("Daemon lebt weiter", d.poll() is None)

# mehrere Auftraege nacheinander
for _ in range(2):
    cli("--full", "--save"); time.sleep(1.5)
check("weitere Auftraege funktionieren", len(saved()) >= n0 + 3, str(len(saved())))

# Ideen-Fenster und Bild oeffnen
p, _ = cli("--ideas"); time.sleep(1.0)
p2, _ = cli("--open", f"{SCR}/data/testbild.png"); time.sleep(1.0)
check("Ideen/Open akzeptiert", p.returncode == 0 and p2.returncode == 0)
check("Daemon lebt nach Fenstern", d.poll() is None)

# Autostart-Helfer
from ksnapmark import system
os.environ["XDG_CONFIG_HOME"] = home + "/.config"
check("Autostart anfangs aus", not system.autostart_enabled())
system.set_autostart(True)
txt = system.autostart_path().read_text()
check("Autostart-Datei", system.autostart_enabled() and "--daemon" in txt and "X-KDE-autostart-after" in txt)
system.set_autostart(False)
check("Autostart entfernt", not system.autostart_enabled())

# --quit beendet den Daemon
p, _ = cli("--quit")
try: d.wait(timeout=10)
except subprocess.TimeoutExpired: pass
check("--quit beendet Daemon", d.poll() is not None)

# veralteter Socket (kill -9) -> Neustart klappt
d = subprocess.Popen([sys.executable, "-m", "ksnapmark", "--daemon"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
wait_up(); d.send_signal(signal.SIGKILL); d.wait()
check("Socket-Datei bleibt veraltet zurueck", os.path.exists(ipc.socket_path()))
d = subprocess.Popen([sys.executable, "-m", "ksnapmark", "--daemon"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
check("Neustart nach Absturz", wait_up() and d.poll() is None)

# erster Aufruf ohne Daemon wird selbst zum Daemon
cli("--quit"); d.wait(timeout=10)
n0 = len(saved())
d = subprocess.Popen([sys.executable, "-m", "ksnapmark", "--full", "--save"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(4)
check("Erstaufruf: speichert und bleibt im Hintergrund", len(saved()) == n0 + 1 and d.poll() is None and wait_up(2))
cli("--quit"); d.wait(timeout=10)

# config resident=false -> Aufruf beendet sich
os.makedirs(home + "/.config/ksnapmark", exist_ok=True)
open(home + "/.config/ksnapmark/config.toml", "w").write("resident = false\n")
n0 = len(saved())
p, _ = cli("--full", "--save")
check("resident=false: Prozess endet", p.returncode == 0 and len(saved()) == n0 + 1 and ipc.send(ipc.Job(action="ping"), timeout=1) is None)

shutil.rmtree(home, ignore_errors=True); shutil.rmtree(run, ignore_errors=True)
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
