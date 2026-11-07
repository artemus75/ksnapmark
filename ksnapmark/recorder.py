"""Bildschirmaufnahme (Video/GIF).

Unter Wayland darf KSnapMark den Bildschirm nicht selbst als Video mitschneiden. Die Aufnahme
übernimmt deshalb Spectacle (ab Plasma 6.x: ``spectacle -b -R r|w|s``); KSnapMark startet sie,
legt die Datei sauber ab und kann sie mit ffmpeg zusätzlich in ein GIF umwandeln.
Beenden einer laufenden Aufnahme: über das Spectacle-Symbol in der Systemleiste.
"""

from __future__ import annotations

from .i18n import tr

import os
import shutil
import subprocess
import time
from pathlib import Path

MODES = {"region": "r", "window": "w", "screen": "s"}
MODE_LABELS = {"region": tr("Region"), "window": tr("Window"), "screen": tr("Screen")}


class RecorderError(RuntimeError):
    pass


_support_cache: bool | None = None


def spectacle_can_record() -> bool:
    """Kennt die installierte Spectacle-Version die Aufnahme-Option?"""
    global _support_cache
    if _support_cache is not None:
        return _support_cache
    exe = shutil.which("spectacle")
    if not exe:
        _support_cache = False
        return False
    try:
        res = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=8)
        text = (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return False  # nicht zwischenspeichern: vielleicht nur ein einmaliger Fehler
    _support_cache = "--record" in text
    return _support_cache


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


MISSING_SPECTACLE = (tr("For screen recordings KSnapMark needs a Spectacle version with recording support (KDE Plasma 6).\n\nInstall/update on Arch:\nsudo pacman -S spectacle\n\nCheck: spectacle --help must show the --record option."))
MISSING_FFMPEG = tr("ffmpeg is missing for converting to GIF.\n\nInstall on Arch:\nsudo pacman -S ffmpeg")


def new_video_path(directory, fmt: str = "webm") -> Path:
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("webm", "mp4"):
        fmt = "webm"
    base = Path(os.path.expanduser(str(directory))) / time.strftime("ksnapmark_%Y-%m-%d_%H-%M-%S")
    path = base.with_suffix("." + fmt)
    n = 2
    while path.exists():
        path = Path(f"{base}-{n}.{fmt}")
        n += 1
    return path


def record_command(mode: str, out: Path) -> list[str]:
    if mode not in MODES:
        raise RecorderError(tr("Unknown recording mode: {mode}").format(mode=mode))
    return ["spectacle", "-b", "-R", MODES[mode], "-o", str(out)]


def gif_command(src: Path, dst: Path, fps: int = 12, width: int = 960) -> list[str]:
    """ffmpeg mit eigener Farbpalette: deutlich bessere GIFs als die Standardpalette."""
    vf = (f"fps={int(fps)},scale='min({int(width)},iw)':-2:flags=lanczos,"
          "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5")
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-loop", "0", str(dst)]


def convert_to_gif(src, dst=None, fps: int = 12, width: int = 960, timeout: int = 600) -> Path:
    src = Path(src)
    if not ffmpeg_available():
        raise RecorderError(MISSING_FFMPEG)
    if not src.is_file() or src.stat().st_size == 0:
        raise RecorderError(tr("Video file not found or empty: {src}").format(src=src))
    dst = Path(dst) if dst else src.with_suffix(".gif")
    if dst.exists():
        n = 2
        while Path(f"{dst.with_suffix('')}-{n}.gif").exists():
            n += 1
        dst = Path(f"{dst.with_suffix('')}-{n}.gif")
    try:
        res = subprocess.run(gif_command(src, dst, fps, width), capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        dst.unlink(missing_ok=True)
        raise RecorderError(f"ffmpeg: {exc}") from exc
    if res.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        raise RecorderError("ffmpeg: " + res.stderr.decode(errors="replace").strip()[-300:])
    return dst
