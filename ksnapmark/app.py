"""Einstiegspunkt: Kommandozeile, Hintergrundprozess (Tray), Ablaufsteuerung, Fensterverwaltung.

Normalbetrieb: Der erste Aufruf startet KSnapMark dauerhaft im Hintergrund (Symbol in der
Systemleiste). Jeder weitere Aufruf – z. B. per Tastenkürzel – schickt nur einen Auftrag an
diesen Prozess und beendet sich sofort. ``--standalone`` arbeitet wie früher ohne Hintergrundprozess.
"""

from __future__ import annotations

from .i18n import tr

import argparse
import os
import sys

from . import __version__, config, ipc, system
from .ipc import Job


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ksnapmark",
        description=tr("Screenshot tool: select a region, edit, share, read text, collect ideas."))
    p.add_argument("--ideas", action="store_true", help=tr("open the ideas collection"))
    p.add_argument("--full", action="store_true", help=tr("capture the full screen instead of a region"))
    p.add_argument("--ocr", action="store_true",
                   help=tr("select a region and put its text straight into the clipboard"))
    p.add_argument("--qr", action="store_true",
                   help=tr("select a region, read the QR code/barcode and put its content into the clipboard"))
    p.add_argument("--pin", action="store_true",
                   help=tr("select a region and pin it as a floating image above the desktop"))
    p.add_argument("--copy", action="store_true",
                   help=tr("select a region and copy it to the clipboard immediately"))
    p.add_argument("--scroll", action="store_true",
                   help=tr("select a region and capture scrolling content (you scroll, KSnapMark stitches)"))
    p.add_argument("--save", action="store_true", help=tr("select a region and save it immediately"))
    p.add_argument("--delay", type=float, default=0.0, metavar="SEK", help=tr("delay before capturing"))
    p.add_argument("--screen", metavar="NAME", help=tr("monitor name (see --doctor)"))
    p.add_argument("--open", metavar="DATEI", help=tr("open an existing image in the editor"))
    p.add_argument("--record", choices=["region", "window", "screen"], metavar="MODUS",
                   help=tr("start a screen recording (video): region, window or screen (via Spectacle)"))
    p.add_argument("--gif", metavar="VIDEO", help=tr("convert an existing video to a GIF (ffmpeg)"))
    p.add_argument("--history", action="store_true", help=tr("open the history with text search"))
    p.add_argument("--settings", action="store_true", help=tr("open the settings"))
    p.add_argument("--daemon", action="store_true",
                   help=tr("only start in the background (tray icon), e.g. at login"))
    p.add_argument("--standalone", action="store_true",
                   help=tr("work without a background process (one call = one process)"))
    p.add_argument("--quit", action="store_true", help=tr("quit the KSnapMark running in the background"))
    p.add_argument("--doctor", action="store_true", help=tr("check the environment and show missing packages"))
    p.add_argument("--selftest", action="store_true",
                   help=tr("thorough test of all features; writes the report to ~/ksnapmark-selftest.txt"))
    p.add_argument("--version", action="version", version=f"ksnapmark {__version__}")
    return p.parse_args(argv)


def job_from_args(args: argparse.Namespace) -> Job:
    if args.quit:
        return Job(action="quit")
    if args.daemon:
        return Job(action="ping")
    if args.ideas:
        return Job(action="ideas")
    if args.settings:
        return Job(action="settings")
    if args.history:
        return Job(action="history")
    if args.record:
        return Job(action="record", mode=args.record)
    if args.gif:
        return Job(action="gif", file=os.path.abspath(args.gif))
    if args.open:
        return Job(action="open", file=os.path.abspath(args.open))
    mode = "ocr" if args.ocr else "qr" if args.qr else "pin" if args.pin else "scroll" if args.scroll else "copy" if args.copy else "save" if args.save else "edit"
    return Job(action="capture", mode=mode, full=args.full, screen=args.screen, delay=args.delay)


class Context:
    """Gemeinsamer Zustand für alle Fenster."""

    def __init__(self) -> None:
        self.cfg = config.load()
        self._store = None
        self._history = None
        self.windows: list = []
        self.last_terms = ""  # zuletzt eingegebene Schwärz-Begriffe (nur im Speicher)

    @property
    def history(self):
        if self._history is None:
            from .history import History

            self._history = History(self.cfg.history_size if self.cfg.history else 0)
        return self._history

    @property
    def store(self):
        if self._store is None:
            from .ideas import IdeaStore

            self._store = IdeaStore()
        return self._store

    def keep(self, window) -> None:
        """Fenster am Leben halten und nach dem Schließen wieder freigeben."""
        from PySide6.QtCore import Qt

        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.windows.append(window)
        window.destroyed.connect(self._prune)

    def _prune(self, *_args) -> None:
        import shiboken6

        self.windows = [w for w in self.windows if shiboken6.isValid(w)]


def doctor() -> int:
    from PySide6.QtGui import QGuiApplication

    from . import capture, ocr

    ok, bad = "✔", "✘"
    cfg = config.load()
    print(f"KSnapMark {__version__}\n")
    session = "Wayland" if system.is_wayland() else ("X11" if os.environ.get("DISPLAY") else "unbekannt")
    print(f"Session:  {session}   Desktop: {os.environ.get('XDG_CURRENT_DESKTOP', '?')}")
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"  # kein Display (z. B. TTY/SSH): Qt nicht abstürzen lassen
    app = None
    try:
        app = QGuiApplication.instance() or QGuiApplication(["ksnapmark"])
        print(f"Qt platform: {QGuiApplication.platformName()}")
        for s in QGuiApplication.screens():
            g = s.geometry()
            print(f"  Monitor {s.name()}: {g.width()}x{g.height()} @ x{s.devicePixelRatio():g}")
    except Exception as exc:  # noqa: BLE001
        print(f"Qt could not start: {exc}")

    print("\nBackground process:")
    reply = ipc.send(Job(action="ping"), timeout=1.5)
    print(f"  {ok if reply is not None else bad} KSnapMark in the background "
          f"{'running' if reply is not None else 'not running (starts by itself on first use)'}")
    print(f"  {ok if system.autostart_enabled() else bad} Autostart at login "
          f"({'on' if system.autostart_enabled() else 'off – can be switched on in the tray menu'})")

    print("\nScreen capture (at least one needed):")
    avail = capture.available_backends()
    labels = {"kwin": "KWin D-Bus (built in, KDE)", "portal": "Desktop portal (built in)"}
    wayland = os.environ.get("WAYLAND_DISPLAY") is not None
    for name in capture.ALL_BACKENDS:
        if wayland and name in capture.X11_ONLY and name not in avail:
            print(f"  – {name} (X11 only, not used here)")
            continue
        print(f"  {ok if name in avail else bad} {labels.get(name, name)}")
    if app is not None and avail:
        worked = False
        for name in capture.backend_order(cfg.capture_backend):
            if name not in avail:
                continue
            if name == "portal" and worked and not os.environ.get("KSNAPMARK_DOCTOR_ALL"):
                print("  – portal test skipped (not needed; use KSNAPMARK_DOCTOR_ALL=1 to run it anyway)")
                continue
            good, secs, detail = capture.test_backend(name)
            print(f"  {ok if good else bad} Test {name}: {secs:.1f} s  {detail}")
            worked = worked or good
        if not worked:
            print("  → No method worked.")
    if not avail and session != "X11":
        print("  → Wayland: sudo pacman -S grim (Sway/Hyprland), spectacle (KDE) or gnome-screenshot (GNOME)")

    print("\nClipboard (so copied content survives closing):")
    for name in ("wl-copy", "xclip"):
        print(f"  {ok if system.which(name) else bad} {name}")

    print("\nText recognition:")
    if ocr.available():
        langs = ocr.installed_langs()
        print(f"  {ok} tesseract  (languages: {', '.join(langs) or 'none'})")
        if "deu" not in langs:
            print("  → German data missing: sudo pacman -S tesseract-data-deu")
    else:
        print(f"  {bad} tesseract → sudo pacman -S tesseract tesseract-data-deu tesseract-data-eng")

    print("\nExtra features:")
    from . import qr, recorder, windows

    qb = qr.backend()
    print(f"  {ok if qb else bad} Read QR codes: " + (f"{qb}" if qb else "sudo pacman -S zbar (or python-opencv)"))
    can_rec = recorder.spectacle_can_record()
    print(f"  {ok if can_rec else bad} Screen recording: " + ("Spectacle with recording support" if can_rec
                                                        else "needs Spectacle from Plasma 6 (spectacle --help must list --record)"))
    print(f"  {ok if recorder.ffmpeg_available() else bad} Create GIFs: ffmpeg")
    snap = app is not None and windows.available()
    print(f"  {ok if snap else bad} Window snapping: " + ("KWin scripting interface reachable" if snap
                                                              else "KDE Plasma (Wayland) only"))
    if snap:
        got = windows.query_windows()
        print(f"     Test: {len(got)} windows detected" if got is not None else "     Test: KWin returned no window list")

    print("\nMisc:")
    for name, why in (("notify-send", "Notifications (libnotify)"), ("curl", "Upload"),
                      ("xdg-open", "Open (xdg-utils)"), ("xdg-email", "E-mail (xdg-utils)")):
        print(f"  {ok if system.which(name) else bad} {name}  – {why}")
    return 0


def _run(cmd: list[str], timeout: int = 8) -> str:
    import subprocess

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return ((res.stdout or "") + (res.stderr or "")).strip()
    except Exception as exc:  # noqa: BLE001
        return f"(not executable: {exc})"


def selftest() -> int:
    """Ausführlicher Test; Bericht auf dem Bildschirm und in ~/ksnapmark-selftest.txt (zum Weiterschicken)."""
    import contextlib
    import io
    import platform
    import time
    from pathlib import Path

    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from . import capture, recorder, windows
    from . import history as history_mod

    app = QApplication.instance() or QApplication(["ksnapmark"])
    out: list[str] = []

    def line(text: str = "") -> None:
        out.append(text)

    def section(title: str) -> None:
        line()
        line(f"=== {title} ===")

    line(f"KSnapMark self-test – {time.strftime('%Y-%m-%d %H:%M:%S')}")
    section("System")
    line(f"Python {platform.python_version()}  PySide6 {pyside_version}  Qt {qVersion()}")
    line(f"Kernel: {platform.release()}")
    for key in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "WAYLAND_DISPLAY", "DISPLAY", "QT_QPA_PLATFORM"):
        line(f"{key}={os.environ.get(key, '')}")
    for label, cmd in (("Plasma", ["plasmashell", "--version"]), ("KWin", ["kwin_wayland", "--version"]),
                       ("Spectacle", ["spectacle", "--version"]), ("ffmpeg", ["ffmpeg", "-version"])):
        if system.which(cmd[0]):
            line(f"{label}: {_run(cmd).splitlines()[0] if _run(cmd) else '?'}")
        else:
            line(f"{label}: not installed")

    section("Environment check (--doctor, without the portal prompt)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        doctor()
    line(buf.getvalue().rstrip())

    section("Tray")
    line(f"System tray available (Qt): {QSystemTrayIcon.isSystemTrayAvailable()}")
    try:
        from PySide6.QtDBus import QDBusConnection

        iface = QDBusConnection.sessionBus().interface()
        watcher = iface.isServiceRegistered("org.kde.StatusNotifierWatcher").value() if iface else False
        line(f"StatusNotifierWatcher on D-Bus: {watcher}")
    except Exception as exc:  # noqa: BLE001
        line(f"D-Bus query not possible: {exc}")
    reply = ipc.send(Job(action="ping"), timeout=1.5)
    line(f"Background process responds: {reply is not None}")

    section("End-to-end capture (as with the shortcut)")
    from .overlay import screens_to_cover

    screens = screens_to_cover(None)
    t0 = time.monotonic()
    shots = capture.capture_screens(screens, config.load().capture_backend)
    dt = time.monotonic() - t0
    line(f"Method: {capture.LAST_BACKEND or 'none'}   Duration: {dt:.2f} s   Monitors captured: {len(shots)} of {len(screens)}")
    for screen, img in shots:
        g = screen.geometry()
        blank = capture._looks_blank(img)
        line(f"  {screen.name()}: image {img.width()}x{img.height()} dpr={img.devicePixelRatio():.2f} "
             f"logical {g.width()}x{g.height()} @({g.x()},{g.y()}) blank={blank}")
    for err in capture.LAST_ERRORS:
        line(f"  Note: {err}")

    section("Window snapping (KWin script)")
    if windows.available():
        t0 = time.monotonic()
        wins = windows.query_windows()
        dt = time.monotonic() - t0
        if wins is None:
            line("KWin returned no window list (script not loaded or no reply).")
        else:
            line(f"{len(wins)} windows in {dt * 1000:.0f} ms. Applications (without window titles): "
                 + ", ".join(sorted({w.app or '?' for w in wins})))
            for w in wins:
                r = w.rect
                line(f"  {w.app or '?'}: {r.width()}x{r.height()} @({r.x()},{r.y()})")
    else:
        line("Not available (KDE Plasma on Wayland only).")

    section("Screen recording (Spectacle)")
    if system.which("spectacle"):
        helptext = _run(["spectacle", "--help"])
        rec = [ln for ln in helptext.splitlines() if "record" in ln.lower() or " -R" in ln or "--background" in ln]
        line("Recording option present: " + str(recorder.spectacle_can_record()))
        line("\n".join(rec) if rec else "(no matching lines in spectacle --help)")
    else:
        line("Spectacle not installed.")

    section("Files and permissions")
    cfg = config.load()
    line(f"Configuration: {config.CONFIG_DIR / 'config.toml'} exists={(config.CONFIG_DIR / 'config.toml').exists()}")
    hist = history_mod.History(cfg.history_size).dir
    line(f"History: {hist} entries={len(history_mod.History(cfg.history_size).entries())}")
    line(f"Autostart entry: {system.autostart_path()} exists={system.autostart_path().exists()} enabled={system.autostart_enabled()}")
    line(f"Save folder: {cfg.save_dir} exists={Path(cfg.save_dir).exists()}")

    report = "\n".join(out) + "\n"
    target = Path.home() / "ksnapmark-selftest.txt"
    try:
        target.write_text(report, encoding="utf-8")
        saved = f"\nReport saved: {target}"
    except OSError as exc:
        saved = f"\nReport could not be saved: {exc}"
    print(report + saved)
    return 0


class Controller:
    """Führt Aufträge aus (Aufnehmen, Ideen, Bild öffnen) und verwaltet das Tray-Symbol."""

    def __init__(self, app, ctx: Context, resident: bool) -> None:
        self.app = app
        self.ctx = ctx
        self.resident = resident
        self.overlays: list = []
        self.capturing = False
        self.exit_code = 0
        self.tray = None
        self.menu = None
        self._history_menu = None
        self._settings_win = None
        self._rec_proc = None
        self.server = None
        self._exit_armed = False

    # --- Aufträge -------------------------------------------------------------------------
    def handle(self, job: Job) -> None:
        if job.action == "quit":
            self.app.quit()
        elif job.action == "ideas":
            self.open_ideas()
        elif job.action == "settings":
            self.open_settings()
        elif job.action == "history":
            self.open_history_window()
        elif job.action == "record":
            self.start_recording(job.mode)
        elif job.action == "gif" and job.file:
            self.make_gif(job.file)
        elif job.action == "open" and job.file:
            from PySide6.QtGui import QImage

            img = QImage(job.file)
            if img.isNull():
                self.fail(tr("Image could not be loaded: {file}").format(file=job.file))
            else:
                self.open_editor(img, 1.0, record=False)
        elif job.action == "capture":
            if self.overlays:  # zweiter Druck auf das Kürzel bricht die laufende Aufnahme ab
                self.cancel_capture()
            elif not self.capturing:
                self.capturing = True
                from PySide6.QtCore import QTimer

                QTimer.singleShot(int(job.delay * 1000) + 150, lambda: self._capture_now(job))
        # "ping": nichts zu tun

    def fail(self, message: str, code: int = 1) -> None:
        print(message, file=sys.stderr)
        system.notify("KSnapMark", message.splitlines()[0])
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(None, "KSnapMark", message)
        self.exit_code = code
        self.job_finished(force_quit_code=code)

    def job_finished(self, force_quit_code: int | None = None) -> None:
        """Ohne Hintergrundprozess endet KSnapMark nach dem Auftrag; sonst bleibt es im Tray."""
        if self.resident:
            return
        if force_quit_code is not None:
            self.app.exit(force_quit_code)
        else:
            self.standalone_exit()

    def standalone_exit(self) -> None:
        from PySide6.QtCore import QTimer

        if system.keepalive_requested() and not self._exit_armed:
            # Qt-Zwischenablage: Prozess bleibt, bis jemand etwas anderes kopiert.
            self._exit_armed = True
            self.app.clipboard().dataChanged.connect(self.app.quit)
            QTimer.singleShot(10 * 60 * 1000, self.app.quit)
        elif not system.keepalive_requested():
            self.app.quit()

    # --- Fenster --------------------------------------------------------------------------
    def open_editor(self, image, dpr: float = 1.0, idea_id: int | None = None,
                    history_name: str | None = None, record: bool = True):
        from .editor import EditorWindow

        win = EditorWindow(image, dpr, self.ctx, idea_id, history_name, record)
        self.ctx.keep(win)
        win.show()
        win.raise_()
        win.activateWindow()
        return win

    def start_scroll(self, screen, region, ratio: float) -> None:
        """Scrolling capture of ``region`` (real pixels of ``screen``)."""
        from . import capture
        from .scroll import ScrollOverlay

        backend = self.ctx.cfg.capture_backend

        def grab():
            shots = capture.capture_screens([screen], backend)
            return shots[0][1].copy(region) if shots else None

        ov = ScrollOverlay(screen, region, ratio, grab)
        self.ctx.keep(ov)
        ov.finished.connect(lambda img: self.open_editor(img, ratio))
        ov.cancelled.connect(self.job_finished)
        ov.start()

    def pin_image(self, image, dpr: float = 1.0):
        from .pin import PinWindow

        win = PinWindow(image, dpr)
        win.open_in_editor.connect(lambda img: self.open_editor(img, 1.0, record=False))
        self.ctx.keep(win)
        win.show()
        win.raise_()
        return win

    # --- Bildschirmaufnahme -----------------------------------------------------------------
    def start_recording(self, mode: str) -> None:
        from PySide6.QtCore import QProcess

        from . import recorder

        if getattr(self, "_rec_proc", None) is not None:
            system.notify("KSnapMark", tr("A recording is already running (stop it via the Spectacle icon)."))
            return
        if not recorder.spectacle_can_record():
            self.fail(recorder.MISSING_SPECTACLE)
            return
        cfg = self.ctx.cfg
        out = recorder.new_video_path(cfg.record_dir, cfg.record_format)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = recorder.record_command(mode, out)
        except (OSError, recorder.RecorderError) as exc:
            self.fail(tr("Capture not possible: {exc}").format(exc=exc))
            return
        proc = QProcess(self.app)
        proc.finished.connect(lambda code, _st, o=out: self._recording_finished(o, code))
        proc.errorOccurred.connect(lambda _e, o=out: self._recording_finished(o, -1))
        proc.start(cmd[0], cmd[1:])
        self._rec_proc = proc
        if self.tray is not None:
            self.tray.setToolTip(tr("KSnapMark – recording (stop it via the Spectacle icon)"))
        system.notify("KSnapMark", tr("Recording started – click the Spectacle icon in the system tray to stop it."))

    def _recording_finished(self, out, code: int) -> None:
        proc, self._rec_proc = getattr(self, "_rec_proc", None), None
        if proc is None:
            return  # Fehler- und Ende-Signal können beide kommen
        if self.tray is not None:
            self.tray.setToolTip(tr("KSnapMark is running – click to start a capture"))
        import time as _time

        for _ in range(20):  # Spectacle schließt die Datei manchmal erst kurz nach dem Prozessende
            if out.exists() and out.stat().st_size > 0:
                break
            _time.sleep(0.1)
        if not out.exists() or out.stat().st_size == 0:
            self.fail(tr("The recording failed (Spectacle, code {code}). File: {out}").format(code=code, out=out))
            return
        system.notify("KSnapMark", tr("Recording saved: {out}").format(out=out))
        if self.ctx.cfg.record_gif:
            self.make_gif(str(out))
        else:
            self.job_finished()

    def make_gif(self, video: str) -> None:
        from pathlib import Path

        from . import recorder
        from .asyncutil import run_async

        if not recorder.ffmpeg_available():
            self.fail(recorder.MISSING_FFMPEG)
            return
        system.notify("KSnapMark", tr("Creating GIF …"))

        def done(path) -> None:
            system.notify("KSnapMark", tr("GIF saved: {path}").format(path=path))
            self.job_finished()

        def failed(msg: str) -> None:
            self.fail(tr("GIF could not be created:\n{msg}").format(msg=msg))

        run_async(lambda: recorder.convert_to_gif(Path(video)), done, failed)

    def pick_video_for_gif(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        start = os.path.expanduser(self.ctx.cfg.record_dir)
        path, _ = QFileDialog.getOpenFileName(None, tr("Choose video"), start,
                                              tr("Videos (*.webm *.mp4 *.mkv *.mov *.avi);;All files (*)"))
        if path:
            self.make_gif(path)

    def open_settings(self):
        from .settings_ui import SettingsDialog

        if getattr(self, "_settings_win", None) is not None:
            try:
                self._settings_win.raise_()
                self._settings_win.activateWindow()
                return
            except RuntimeError:  # Fenster wurde schon zerstört
                self._settings_win = None
        win = SettingsDialog(self.ctx.cfg, self.ctx.history)
        win.setWindowIcon(self.app.windowIcon())
        win.saved.connect(self.apply_config)
        win.destroyed.connect(lambda *_: setattr(self, "_settings_win", None))
        self._settings_win = win
        self.ctx.keep(win)
        win.show()
        win.raise_()
        win.activateWindow()

    def apply_config(self) -> None:
        """Nach dem Speichern der Einstellungen: abhängige Teile neu aufbauen."""
        self.ctx._history = None  # neue Verlaufsgröße übernehmen
        if self._history_menu is not None:
            self._history_menu.menuAction().setVisible(self.ctx.cfg.history and self.ctx.cfg.history_size > 0)
            self.fill_history_menu()

    def open_ideas(self):
        from .ideas_ui import IdeasWindow

        win = IdeasWindow(self.ctx.store, self.ctx.cfg.ocr_langs,
                          lambda img, iid: self.open_editor(img, 1.0, iid, record=False))
        self.ctx.keep(win)
        win.show()
        win.raise_()
        win.activateWindow()

    # --- Aufnahme -------------------------------------------------------------------------
    def cancel_capture(self) -> None:
        for o in self.overlays:
            o.close()
        self.overlays = []
        self.capturing = False
        self.job_finished()

    def _capture_now(self, job: Job) -> None:
        from . import capture
        from .overlay import SelectionOverlay, current_screen, screens_to_cover

        # --full: nur der Monitor unter dem Mauszeiger; sonst Overlay auf jedem Monitor
        screens = [current_screen(job.screen)] if job.full else screens_to_cover(job.screen)
        wins = None
        if not job.full and self.ctx.cfg.snap_windows:
            try:
                from . import windows

                wins = windows.query_windows()  # vor dem Overlay, sonst wäre dieses selbst in der Liste
            except Exception:  # noqa: BLE001 - ohne Fensterliste geht die Auswahl normal weiter
                wins = None
        shots = capture.capture_screens(screens, self.ctx.cfg.capture_backend)
        if not shots:
            self.capturing = False
            self.fail(capture.failure_message(), 2)
            return
        overlays: list = []
        self.overlays = overlays
        for screen, shot in shots:
            overlay = SelectionOverlay(screen, shot, wins)
            overlays.append(overlay)
            self.ctx.keep(overlay)
            overlay.selected.connect(
                lambda img, r, j=job, ovs=overlays, o=overlay: self.handle_region(j, ovs, img, r, o))
            overlay.cancelled.connect(self.cancel_capture)

        if job.full:
            screen, shot = shots[0]
            img = shot.copy()
            img.setDevicePixelRatio(1.0)
            self.handle_region(job, overlays, img, shot.width() / max(1, screen.geometry().width()), overlays[0])
        else:
            for overlay in overlays:
                overlay.show_on_screen()
            overlays[0].activateWindow()

    def handle_region(self, job: Job, overlays: list, image, ratio: float, overlay=None) -> None:
        """Ein Bereich wurde gewählt (oder der ganze Bildschirm)."""
        if self.overlays is overlays:
            self.overlays = []
        self.capturing = False
        if job.mode == "scroll" and overlay is not None:
            from PySide6.QtCore import QRect

            region = overlay.region or QRect(0, 0, image.width(), image.height())
            screen = overlay._screen
            for o in overlays:
                o.close()
            self.app.processEvents()
            self.start_scroll(screen, region, ratio)
            return
        if job.mode != "edit":
            for o in overlays:
                o.hide()
            self.app.processEvents()
            self.run_direct(job, image, ratio)
            for o in overlays:
                o.close()
            return
        self.open_editor(image, ratio)
        for o in overlays:
            o.close()

    def run_direct(self, job: Job, image, ratio: float = 1.0) -> None:
        from . import ocr
        from .qr import QrError

        cfg = self.ctx.cfg
        try:
            if job.mode == "ocr":
                text = ocr.ocr_text(image, cfg.ocr_langs)
                if not text.strip():
                    system.notify("KSnapMark", tr("No text recognized."))
                elif system.clipboard_set_text(text):
                    system.notify("KSnapMark", tr("Text copied ({n} characters)").format(n=len(text)))
                else:
                    self.app.clipboard().setText(text)
                    system.request_keepalive()
                    system.notify("KSnapMark", tr("Text copied ({n} characters)").format(n=len(text)))
            elif job.mode == "pin":
                self.pin_image(image, ratio)
                return  # Fenster bleibt offen: Auftrag nicht „beenden“
            elif job.mode == "qr":
                from . import qr

                codes = qr.decode(image)
                if not codes:
                    system.notify("KSnapMark", tr("No QR code or barcode found."))
                else:
                    text = codes[0].data
                    if not system.clipboard_set_text(text):
                        self.app.clipboard().setText(text)
                        system.request_keepalive()
                    more = tr(" (+{n} more)").format(n=len(codes) - 1) if len(codes) > 1 else ""
                    system.notify("KSnapMark", tr("Code copied{more}: {text}").format(more=more, text=text[:120]))
            elif job.mode == "copy":
                from .editor import png_bytes

                if not system.clipboard_set(png_bytes(image), "image/png"):
                    self.app.clipboard().setImage(image)
                    system.request_keepalive()
                self.ctx.history.add(image)
                system.notify("KSnapMark", tr("Screenshot copied"))
            elif job.mode == "save":
                path = system.unique_screenshot_path(cfg.save_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(path), "PNG")
                self.ctx.history.add(image)
                system.notify("KSnapMark", tr("Saved: {path}").format(path=path))
        except (ocr.OcrError, QrError) as exc:
            self.fail(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.fail(tr("Error: {exc}").format(exc=exc))
            return
        self.job_finished()

    # --- Verlauf --------------------------------------------------------------------------
    def fill_history_menu(self) -> None:
        """Untermenü mit den letzten Aufnahmen (Vorschaubild, Uhrzeit) neu aufbauen."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction, QIcon, QPixmap

        menu = self._history_menu
        menu.clear()
        entries = self.ctx.history.entries()
        find = QAction(tr("Search history …"), menu)
        find.triggered.connect(self.open_history_window)
        menu.addAction(find)
        menu.addSeparator()
        if not entries:
            empty = QAction(tr("No captures yet"), menu)
            empty.setEnabled(False)
            menu.addAction(empty)
            return
        for e in entries:
            pm = QPixmap(str(e.path))
            act = QAction(_history_label(e), menu)
            if not pm.isNull():
                act.setText(f"{_history_label(e)}  ({pm.width()}×{pm.height()})")
                act.setIcon(QIcon(pm.scaled(64, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)))
            act.triggered.connect(lambda _=False, n=e.name: self.open_history(n))
            menu.addAction(act)
        menu.addSeparator()
        clear = QAction(tr("Clear history"), menu)
        clear.triggered.connect(self.ctx.history.clear)
        menu.addAction(clear)

    def open_history_window(self) -> None:
        """Window with thumbnails and text search over the history."""
        from .history_ui import HistoryDialog

        cfg = self.ctx.cfg
        dlg = HistoryDialog(self.ctx.history, cfg.ocr_langs, cfg.history_ocr)
        dlg.open_entry.connect(self.open_history)
        self.ctx.keep(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_history(self, name: str) -> None:
        img = self.ctx.history.load(name)
        if img is None:
            self.fail(tr("The entry no longer exists."))
            return
        self.open_editor(img, 1.0, history_name=name, record=False)

    # --- Tray -----------------------------------------------------------------------------
    def setup_tray(self, attempts: int = 20) -> None:
        """Tray-Symbol anlegen. Beim Anmelden ist die Leiste oft noch nicht da – dann erneut versuchen."""
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        from .icons import app_icon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            if attempts > 0:
                QTimer.singleShot(3000, lambda: self.setup_tray(attempts - 1))
            else:
                print(tr("KSnapMark: no system tray found – continuing without an icon."), file=sys.stderr)
            return

        menu = QMenu()
        self.menu = menu

        def add(text: str, job: Job) -> None:
            act = QAction(text, menu)
            act.triggered.connect(lambda _=False, j=job: self.handle(j))
            menu.addAction(act)

        add(tr("Capture region"), Job(delay=0.2))
        add(tr("Capture full screen"), Job(full=True, delay=0.2))
        add(tr("Copy text from region (OCR)"), Job(mode="ocr", delay=0.2))
        add(tr("Read QR code from region"), Job(mode="qr", delay=0.2))
        add(tr("Pin region (floating)"), Job(mode="pin", delay=0.2))
        add(tr("Scrolling capture"), Job(mode="scroll", delay=0.2))
        rec = menu.addMenu(tr("Screen recording (video)"))
        for key, label in (("region", tr("Record region …")), ("window", tr("Record window …")),
                           ("screen", tr("Record screen …"))):
            act = QAction(label, rec)
            act.triggered.connect(lambda _=False, m=key: self.handle(Job(action="record", mode=m)))
            rec.addAction(act)
        rec.addSeparator()
        gif_act = QAction(tr("Convert video to GIF …"), rec)
        gif_act.triggered.connect(self.pick_video_for_gif)
        rec.addAction(gif_act)
        menu.addSeparator()
        add(tr("open the ideas collection"), Job(action="ideas"))
        self._history_menu = menu.addMenu(tr("History"))
        self._history_menu.aboutToShow.connect(self.fill_history_menu)
        self._history_menu.menuAction().setVisible(self.ctx.cfg.history and self.ctx.cfg.history_size > 0)
        self.fill_history_menu()
        menu.addSeparator()
        add(tr("Settings …"), Job(action="settings"))
        auto = QAction(tr("Start at login"), menu)
        auto.setCheckable(True)
        auto.setChecked(system.autostart_enabled())

        def toggle_autostart(checked: bool) -> None:
            if not system.set_autostart(checked):
                auto.setChecked(system.autostart_enabled())
                self.tray.showMessage("KSnapMark", tr("Autostart could not be changed."))

        auto.toggled.connect(toggle_autostart)
        menu.addAction(auto)
        quit_act = QAction(tr("Quit KSnapMark"), menu)
        quit_act.triggered.connect(self.app.quit)
        menu.addAction(quit_act)

        tray = QSystemTrayIcon(app_icon(), self.app)
        tray.setToolTip(tr("KSnapMark is running – click to start a capture"))
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.handle(Job(delay=0.2))
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        self.tray = tray


def _history_label(entry) -> str:
    from datetime import datetime

    t = datetime.fromtimestamp(entry.taken)
    return t.strftime("%H:%M:%S") if t.date() == datetime.now().date() else t.strftime(tr("%m-%d %H:%M"))



def _install_qt_translations(app) -> None:
    """Qt's own texts (standard buttons, file dialogs) in the active language."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    from . import i18n

    if i18n.LANG == "en":
        return
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase", "qt"):
        translator = QTranslator(app)
        if translator.load(f"{name}_{i18n.LANG}", path):
            app.installTranslator(translator)

def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.doctor:
        return doctor()
    if args.selftest:
        return selftest()
    job = job_from_args(args)

    # Schneller Weg: läuft schon ein Hintergrundprozess, nur den Auftrag übergeben (ohne Qt zu laden).
    if not args.standalone:
        reply = ipc.send(job)
        if reply is not None:
            if reply.get("ok"):
                if args.daemon:
                    print(tr("KSnapMark is already running in the background."))
                return 0
            print(f"KSnapMark: {reply.get('error', 'job rejected')}", file=sys.stderr)
            return 1
        if args.quit:
            print(tr("KSnapMark is not running in the background."))
            return 0
    elif args.quit or args.daemon:
        print(tr("--standalone does not combine with --quit/--daemon."), file=sys.stderr)
        return 2

    cfg = config.load()
    resident = (not args.standalone) and cfg.resident

    from PySide6.QtCore import QThreadPool, QTimer
    from PySide6.QtWidgets import QApplication

    from .icons import app_icon
    from .style import STYLE

    app = QApplication(["ksnapmark"])
    app.setApplicationName("ksnapmark")
    app.setDesktopFileName("ksnapmark")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    _install_qt_translations(app)
    app.setWindowIcon(app_icon())

    ctx = Context()
    ctrl = Controller(app, ctx, resident)

    if resident:
        ctrl.server = ipc.make_server(ctrl.handle, app)
        if ctrl.server is None:
            print(tr("KSnapMark: the background process cannot listen – working without it."), file=sys.stderr)
            ctrl.resident = resident = False
        else:
            ctrl.setup_tray()
            if not args.daemon:
                # Erster Aufruf per Kürzel: dauerhaft im Hintergrund bleiben, das einmalig mitteilen.
                QTimer.singleShot(1500, lambda: ctrl.tray and ctrl.tray.showMessage(
                    "KSnapMark", tr("Now running in the background (icon in the panel).")))
    if not resident:
        app.lastWindowClosed.connect(ctrl.standalone_exit)

    if job.action != "ping":
        QTimer.singleShot(0, lambda: ctrl.handle(job))
    elif not resident:
        return 0  # --daemon ohne Hintergrundbetrieb ergibt keinen Sinn

    code = app.exec()
    QThreadPool.globalInstance().waitForDone(30000)
    return code or ctrl.exit_code


if __name__ == "__main__":
    sys.exit(main())
