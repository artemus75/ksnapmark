"""Konfiguration: optionale Datei ~/.config/ksnapmark/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _xdg(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or (Path.home() / default))


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "ksnapmark"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "ksnapmark"


def migrate_legacy() -> None:
    """Übernimmt Daten der früheren Version (Name „snapmark“) einmalig in die neuen Ordner."""
    for new in (CONFIG_DIR, DATA_DIR):
        old = new.with_name("snapmark")
        try:
            if old.is_dir() and not new.exists():
                old.rename(new)
        except OSError:
            pass


migrate_legacy()


@dataclass
class Config:
    save_dir: Path
    ocr_langs: str = "deu+eng"
    upload_url: str = "https://0x0.st"
    upload_expires_hours: int = 24
    capture_backend: str = "auto"
    resident: bool = True
    history: bool = True
    history_size: int = 10
    history_ocr: bool = True   # index the text of history images (OCR) for the history search
    snap_windows: bool = True
    record_dir: str = "~/Videos"
    record_format: str = "webm"
    record_gif: bool = False
    language: str = "auto"      # auto | en | de
    include_cursor: bool = False  # capture the mouse pointer, too
    auto_copy: bool = True      # new screenshots are put into the clipboard right away
    show_loupe: bool = False  # magnifier + color value next to the pointer while selecting


def load() -> Config:
    data: dict = {}
    path = CONFIG_DIR / "config.toml"
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
    save_dir = Path(os.path.expanduser(str(data.get("save_dir", "~/Pictures/Screenshots"))))
    return Config(
        save_dir=save_dir,
        ocr_langs=str(data.get("ocr_langs", "deu+eng")),
        upload_url=str(data.get("upload_url", "https://0x0.st")),
        upload_expires_hours=int(data.get("upload_expires_hours", 24)),
        capture_backend=str(data.get("capture_backend", "auto")),
        resident=bool(data.get("resident", True)),
        history=bool(data.get("history", True)),
        history_size=int(data.get("history_size", 10)),
        history_ocr=bool(data.get("history_ocr", True)),
        snap_windows=bool(data.get("snap_windows", True)),
        record_dir=str(data.get("record_dir", "~/Videos")),
        record_format=str(data.get("record_format", "webm")),
        record_gif=bool(data.get("record_gif", False)),
        language=str(data.get("language", "auto")),
        include_cursor=bool(data.get("include_cursor", False)),
        show_loupe=bool(data.get("show_loupe", False)),
        auto_copy=bool(data.get("auto_copy", True)),
    )


def _toml_value(value) -> str:
    import json

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)  # JSON-Zeichenkette ist gültiges TOML


def save(cfg: Config) -> None:
    """Konfiguration schreiben. Unbekannte Schlüssel der bestehenden Datei bleiben erhalten."""
    path = CONFIG_DIR / "config.toml"
    extra: dict = {}
    if path.exists():
        try:
            extra = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            extra = {}
    home = str(Path.home())
    save_dir = str(cfg.save_dir)
    if save_dir == home or save_dir.startswith(home + os.sep):
        save_dir = "~" + save_dir[len(home):]
    values = {
        "save_dir": save_dir,
        "ocr_langs": cfg.ocr_langs,
        "upload_url": cfg.upload_url,
        "upload_expires_hours": cfg.upload_expires_hours,
        "capture_backend": cfg.capture_backend,
        "resident": cfg.resident,
        "history": cfg.history,
        "history_size": cfg.history_size,
        "history_ocr": cfg.history_ocr,
        "snap_windows": cfg.snap_windows,
        "record_dir": cfg.record_dir,
        "record_format": cfg.record_format,
        "record_gif": cfg.record_gif,
        "language": cfg.language,
        "include_cursor": cfg.include_cursor,
        "show_loupe": cfg.show_loupe,
        "auto_copy": cfg.auto_copy,
    }
    for key, value in extra.items():
        if key not in values and isinstance(value, (str, int, float, bool)):
            values[key] = value
    lines = ["# KSnapMark settings (also editable via the tray menu)"]
    lines += [f"{k} = {_toml_value(v)}" for k, v in values.items()]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
