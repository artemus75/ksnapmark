"""Anbindung ans System: Zwischenablage, Benachrichtigungen, Programme öffnen."""

from __future__ import annotations

from .i18n import tr

import os
import shutil
import subprocess

_KEEPALIVE = False


def which(name: str) -> str | None:
    return shutil.which(name)


def is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def request_keepalive() -> None:
    """Prozess nach dem Schließen am Leben halten (Qt-Zwischenablage-Fallback)."""
    global _KEEPALIVE
    _KEEPALIVE = True


def keepalive_requested() -> bool:
    return _KEEPALIVE


def _spawn_with_stdin(cmd: list[str], data: bytes) -> bool:
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(data)
        proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return True  # Werkzeug hält die Auswahl im Vordergrund – das ist ok
        return proc.returncode == 0
    except Exception:
        return False


def clipboard_set(data: bytes, mime: str = "text/plain") -> bool:
    """Daten dauerhaft in die Zwischenablage legen (überlebt das Prozessende).

    Qt selbst gibt den Inhalt frei, sobald der Prozess endet. wl-copy / xclip
    halten ihn im Hintergrund vor – deshalb gehen wir diesen Weg zuerst.
    """
    if is_wayland() and which("wl-copy"):
        cmd = ["wl-copy", "--type", mime]
        if _spawn_with_stdin(cmd, data):
            return True
    if os.environ.get("DISPLAY") and which("xclip"):
        cmd = ["xclip", "-selection", "clipboard", "-t", mime, "-i"]
        if _spawn_with_stdin(cmd, data):
            return True
    return False


def clipboard_set_text(text: str) -> bool:
    return clipboard_set(text.encode("utf-8"), "text/plain")


def notify(title: str, body: str = "") -> None:
    exe = which("notify-send")
    if not exe:
        return
    try:
        subprocess.Popen(
            [exe, "-a", "KSnapMark", "-i", "camera-photo", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def open_path(path: str) -> bool:
    exe = which("xdg-open")
    if not exe:
        return False
    try:
        subprocess.Popen([exe, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except Exception:
        return False


def email_with_attachment(path: str, subject: str = "Screenshot") -> bool:
    exe = which("xdg-email")
    if not exe:
        return False
    try:
        subprocess.Popen([exe, "--subject", subject, "--attach", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except Exception:
        return False


def upload_file(path: str, url: str, expires_hours: int) -> str:
    """Datei per curl hochladen (0x0.st-kompatibel) und die zurückgegebene URL liefern."""
    curl = which("curl")
    if not curl:
        raise RuntimeError(tr("curl is not installed (sudo pacman -S curl)."))
    cmd = [curl, "-sS", "--fail", "-A", "KSnapMark/0.1", "-F", f"file=@{path}"]
    if expires_hours > 0:
        cmd += ["-F", f"expires={expires_hours}"]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or tr("Upload failed."))
    out = res.stdout.strip()
    if not out.startswith("http"):
        raise RuntimeError(tr("Unexpected response from the server: {out}").format(out=out[:200]))
    return out


# --- Autostart (XDG) ----------------------------------------------------------------------

def autostart_path():
    from pathlib import Path

    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "ksnapmark-daemon.desktop"


def launcher_path() -> str:
    """Pfad des Startskripts (für Autostart-Eintrag)."""
    import shutil
    from pathlib import Path

    found = shutil.which("ksnapmark")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "ksnapmark"
    return str(local if local.exists() else "ksnapmark")


def _system_autostart() -> bool:
    """Gibt es einen Autostart-Eintrag aus dem Paket (/etc/xdg/autostart)?"""
    from pathlib import Path

    dirs = (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":")
    return any((Path(d) / "autostart" / "ksnapmark-daemon.desktop").exists() for d in dirs if d)


def autostart_enabled() -> bool:
    path = autostart_path()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return True
        return not any(line.strip().lower() == "hidden=true" for line in text.splitlines())
    return _system_autostart()


def set_autostart(enabled: bool) -> bool:
    path = autostart_path()
    try:
        if enabled and _system_autostart():
            path.unlink(missing_ok=True)  # der Eintrag aus dem Paket gilt wieder
        elif enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=KSnapMark\n"
                "Comment=Screenshot-Werkzeug im Hintergrund (Tray-Symbol)\n"
                f"Exec={launcher_path()} --daemon\n"
                "Icon=ksnapmark\n"
                "Terminal=false\n"
                "X-KDE-autostart-after=panel\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8")
        elif _system_autostart():  # Paket-Eintrag per Benutzerdatei außer Kraft setzen
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[Desktop Entry]\nType=Application\nName=KSnapMark\nHidden=true\n",
                            encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def unique_screenshot_path(directory) -> "Path":
    """Dateiname mit Zeitstempel; bei gleicher Sekunde wird -2, -3 … angehängt (nichts überschreiben)."""
    from datetime import datetime
    from pathlib import Path

    base = Path(directory) / datetime.now().strftime("ksnapmark_%Y-%m-%d_%H-%M-%S")
    path = base.with_suffix(".png")
    n = 2
    while path.exists():
        path = Path(f"{base}-{n}.png")
        n += 1
    return path
