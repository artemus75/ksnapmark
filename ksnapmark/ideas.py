"""Ideen-Sammlung: SQLite-Datenbank + Bilddateien unter ~/.local/share/ksnapmark."""

from __future__ import annotations

from .i18n import tr

import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRunnable, Qt
from PySide6.QtGui import QImage

from . import ocr
from .config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    image_file TEXT NOT NULL
);
"""

THUMB_WIDTH = 480


@dataclass
class Idea:
    id: int
    created: str
    title: str
    note: str
    tags: str
    source: str
    ocr_text: str
    image_path: Path
    thumb_path: Path

    @property
    def tag_list(self) -> list[str]:
        return [t for t in self.tags.split(",") if t]


def normalize_tags(raw: str) -> str:
    seen: list[str] = []
    for tag in re.split(r"[,;\s]+", raw.replace("#", " ")):
        tag = tag.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return ",".join(seen)


class IdeaStore:
    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else DATA_DIR
        self.img_dir = self.base / "ideas"
        self.thumb_dir = self.base / "thumbs"
        self.db_path = self.base / "ideas.db"
        self.img_dir.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c, c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _from_row(self, row: sqlite3.Row) -> Idea:
        stem = Path(row["image_file"]).stem
        return Idea(
            id=row["id"], created=row["created"], title=row["title"], note=row["note"],
            tags=row["tags"], source=row["source"], ocr_text=row["ocr_text"],
            image_path=self.img_dir / row["image_file"],
            thumb_path=self.thumb_dir / f"{stem}.png",
        )

    def _write_images(self, image: QImage, filename: str) -> None:
        if not image.save(str(self.img_dir / filename), "PNG"):
            raise OSError(tr("The image could not be saved."))
        thumb = image
        if image.width() > THUMB_WIDTH:
            thumb = image.scaledToWidth(THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
        thumb.save(str(self.thumb_dir / f"{Path(filename).stem}.png"), "PNG")

    # --- Schreiben -------------------------------------------------------
    def add(self, image: QImage, title: str = "", tags: str = "", note: str = "",
            source: str = "") -> int:
        now = datetime.now()
        filename = f"{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.png"
        self._write_images(image, filename)
        title = title.strip() or tr("Idea {now:%Y-%m-%d %H:%M}").format(now=now)
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "INSERT INTO ideas(created,title,note,tags,source,image_file) VALUES(?,?,?,?,?,?)",
                (now.isoformat(timespec="seconds"), title, note.strip(),
                 normalize_tags(tags), source.strip(), filename))
            return int(cur.lastrowid)

    def update(self, idea_id: int, title: str, tags: str, note: str, source: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute("UPDATE ideas SET title=?, tags=?, note=?, source=? WHERE id=?",
                      (title.strip(), normalize_tags(tags), note.strip(), source.strip(), idea_id))

    def replace_image(self, idea_id: int, image: QImage) -> None:
        idea = self.get(idea_id)
        if idea is None:
            return
        self._write_images(image, idea.image_path.name)
        self.set_ocr(idea_id, "")

    def set_ocr(self, idea_id: int, text: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute("UPDATE ideas SET ocr_text=? WHERE id=?", (text, idea_id))

    def delete(self, idea_id: int) -> None:
        idea = self.get(idea_id)
        if idea is None:
            return
        with closing(self._conn()) as c, c:
            c.execute("DELETE FROM ideas WHERE id=?", (idea_id,))
        for path in (idea.image_path, idea.thumb_path):
            try:
                path.unlink()
            except OSError:
                pass

    # --- Lesen -----------------------------------------------------------
    def get(self, idea_id: int) -> Idea | None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone()
        return self._from_row(row) if row else None

    def search(self, query: str = "", tag: str = "") -> list[Idea]:
        sql = "SELECT * FROM ideas"
        where: list[str] = []
        args: list[str] = []
        for token in query.split():
            like = f"%{token}%"
            where.append("(title LIKE ? OR note LIKE ? OR tags LIKE ? OR source LIKE ? OR ocr_text LIKE ?)")
            args += [like] * 5
        if tag:
            where.append("(',' || tags || ',') LIKE ?")
            args.append(f"%,{tag},%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created DESC, id DESC"
        with closing(self._conn()) as c:
            rows = c.execute(sql, args).fetchall()
        return [self._from_row(r) for r in rows]

    def tag_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        with closing(self._conn()) as c:
            for (tags,) in c.execute("SELECT tags FROM ideas"):
                for t in tags.split(","):
                    if t:
                        counts[t] = counts.get(t, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


class _IndexJob(QRunnable):
    """Schreibt den erkannten Text im Hintergrund in die Datenbank (macht Ideen durchsuchbar)."""

    def __init__(self, store: IdeaStore, idea_id: int, langs: str):
        super().__init__()
        self.store = store
        self.idea_id = idea_id
        self.langs = langs

    def run(self) -> None:
        try:
            idea = self.store.get(self.idea_id)
            if idea is None:
                return
            text = ocr.ocr_text(QImage(str(idea.image_path)), self.langs)
            self.store.set_ocr(self.idea_id, text)
        except Exception:
            pass


def start_ocr_index(store: IdeaStore, idea_id: int, langs: str) -> None:
    if not ocr.available():
        return
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().start(_IndexJob(store, idea_id, langs))
