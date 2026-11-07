"""Verlauf der letzten Aufnahmen (für das Tray-Menü).

Die Bilder liegen als PNG unter ``~/.local/share/ksnapmark/history`` (Ordner nur für den
Benutzer lesbar). Anzahl begrenzen oder abschalten: ``history_size`` / ``history`` in der Konfiguration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

from .config import DATA_DIR

_NAME = re.compile(r"^h_(\d{8})_(\d{6})_(\d{3})\.png$")


@dataclass
class Entry:
    name: str
    path: Path
    taken: float  # Unix-Zeit


class History:
    def __init__(self, limit: int = 10, directory: Path | None = None) -> None:
        self.dir = directory or (DATA_DIR / "history")
        self.limit = max(0, int(limit))
        self._last_hash: dict[str, str] = {}
        self._index: dict[str, str] | None = None   # image name -> recognized text (search index)

    # --- Suchindex (Text der Bilder, nur lokal) ----------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.dir / "index.json"

    def _load_index(self) -> dict[str, str]:
        if self._index is None:
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._index = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
            except (OSError, ValueError, AttributeError):
                self._index = {}
        return self._index

    def _save_index(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.dir, 0o700)
            tmp = self.index_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._load_index(), ensure_ascii=False), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.index_path)
        except OSError:
            pass

    def text_of(self, name: str) -> str | None:
        """Erkannter Text eines Eintrags; ``None`` = noch nicht indexiert."""
        return self._load_index().get(name)

    def set_text(self, name: str, text: str) -> None:
        if not _NAME.match(name):
            return
        self._load_index()[name] = text
        self._save_index()

    def missing(self) -> list[Entry]:
        """Einträge ohne Index (neueste zuerst)."""
        index = self._load_index()
        return [e for e in self.entries() if e.name not in index]

    def search(self, query: str) -> list[Entry]:
        """Einträge, deren Text alle Suchwörter enthält (Groß-/Kleinschreibung egal). Leer = alle."""
        words = query.casefold().split()
        entries = self.entries()
        if not words:
            return entries
        index = self._load_index()
        return [e for e in entries
                if all(w in index.get(e.name, "").casefold() for w in words)]

    def _drop_index(self, names) -> None:
        index = self._load_index()
        changed = False
        for n in names:
            if index.pop(n, None) is not None:
                changed = True
        if changed:
            self._save_index()

    # --- Lesen ----------------------------------------------------------------------------
    def entries(self) -> list[Entry]:
        """Neueste zuerst."""
        try:
            names = [n for n in os.listdir(self.dir) if _NAME.match(n)]
        except OSError:
            return []
        out = []
        for n in sorted(names, reverse=True):
            p = self.dir / n
            try:
                out.append(Entry(n, p, p.stat().st_mtime))
            except OSError:
                continue
        return out

    def load(self, name: str) -> QImage | None:
        if not _NAME.match(name):
            return None
        img = QImage(str(self.dir / name))
        return None if img.isNull() else img

    # --- Schreiben ------------------------------------------------------------------------
    def add(self, image: QImage, replace: str | None = None) -> str | None:
        """Bild ablegen. ``replace``: Name eines früheren Eintrags derselben Sitzung (wird ersetzt).

        Gibt den Namen des Eintrags zurück (oder None, wenn der Verlauf aus ist / nicht schreibbar).
        """
        if self.limit <= 0 or image.isNull():
            return None
        digest = hashlib.md5(bytes(image.constBits())[: image.sizeInBytes()], usedforsecurity=False).hexdigest()
        if replace and self._last_hash.get(replace) == digest and (self.dir / replace).exists():
            return replace  # unverändert
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.dir, 0o700)
            if replace and _NAME.match(replace):
                (self.dir / replace).unlink(missing_ok=True)
                self._last_hash.pop(replace, None)
                self._drop_index([replace])
            stamp = time.strftime("%Y%m%d_%H%M%S")
            ms = int((time.time() % 1) * 1000)
            name = f"h_{stamp}_{ms:03d}.png"
            path = self.dir / name
            if not image.save(str(path), "PNG"):
                return None
            os.chmod(path, 0o600)
        except OSError:
            return None
        self._last_hash[name] = digest
        self.prune()
        return name

    def prune(self) -> None:
        old = self.entries()[self.limit:]
        for e in old:
            e.path.unlink(missing_ok=True)
        self._drop_index([e.name for e in old])
        existing = {e.name for e in self.entries()}        # also entries whose file vanished
        self._drop_index([n for n in list(self._load_index()) if n not in existing])

    def delete(self, name: str) -> bool:
        if not _NAME.match(name):
            return False
        try:
            (self.dir / name).unlink(missing_ok=True)
        except OSError:
            return False
        self._last_hash.pop(name, None)
        self._drop_index([name])
        return True

    def clear(self) -> int:
        n = 0
        for e in self.entries():
            try:
                e.path.unlink()
                n += 1
            except OSError:
                pass
        self._last_hash.clear()
        self._index = {}
        self.index_path.unlink(missing_ok=True)
        return n
