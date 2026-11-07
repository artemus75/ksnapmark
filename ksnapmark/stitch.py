"""Vertical stitching of screenshots taken while the content scrolls (scrolling capture)."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

MAX_HEIGHT = 40000       # stop here (pixels) to keep memory in check
MATCH_TOLERANCE = 2.0    # mean gray-value difference (0..255) accepted for a matching strip


def to_array(img: QImage) -> np.ndarray:
    """QImage -> (h, w, 4) uint8 array (BGRA byte order of Format_RGB32)."""
    img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.bytesPerLine() * h)
    return buf.reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :].copy()


def to_image(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    arr = np.ascontiguousarray(arr)
    return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGB32).copy()


def _gray(arr: np.ndarray) -> np.ndarray:
    """Cheap gray version, every 4th column only (speed)."""
    return arr[:, ::4, :3].astype(np.int16).sum(axis=2) // 3


def find_shift(prev: np.ndarray, frame: np.ndarray) -> int | None:
    """How many pixels the content moved up between ``prev`` and ``frame``.

    ``0``: nothing changed. ``None``: no reliable match (scrolled too far, or content changed).
    Fixed headers/footers do not matter, because a strip from the upper part of the frame is searched.
    """
    if prev.shape != frame.shape:
        return None
    gp, gf = _gray(prev), _gray(frame)
    h = gp.shape[0]
    if np.abs(gp - gf).mean() < 0.3:
        return 0
    k = max(8, min(48, h // 6))
    if h < k * 3:
        return None
    for y0 in (h // 5, h // 3, h // 2):
        strip = gf[y0:y0 + k]
        if strip.std() < 3:      # blank area: useless for matching
            continue
        best_p, best_err = None, None
        for p in range(y0 + 1, h - k + 1):
            err = np.abs(gp[p:p + k] - strip).mean()
            if best_err is None or err < best_err:
                best_p, best_err = p, err
        if best_p is not None and best_err is not None and best_err <= MATCH_TOLERANCE:
            return best_p - y0
    return None


def footer_rows(prev: np.ndarray, frame: np.ndarray) -> int:
    """Height of a fixed footer: bottom rows that are (nearly) identical in both frames.

    A row counts as identical if fewer than 4 % of its pixels differ noticeably, so a clock that
    ticks over in a status bar does not break the detection.
    """
    gp, gf = _gray(prev), _gray(frame)
    h = gp.shape[0]
    limit = h // 2
    f = 0
    while f < limit:
        d = np.abs(gp[h - 1 - f] - gf[h - 1 - f])
        if (d > 16).mean() >= 0.04:
            break
        f += 1
    return f


class ScrollSession:
    """Collects frames of the same region and appends only the rows that are new.

    Page coordinates: ``top`` is where the latest frame starts on the (virtual) tall page, ``covered``
    how many page rows are already in ``parts``. A fixed footer is never committed, it is appended once
    at the end (it is part of the last frame's uncommitted rows).
    """

    def __init__(self) -> None:
        self.parts: list[np.ndarray] = []
        self.prev: np.ndarray | None = None
        self.top = 0
        self.covered = 0
        self.height = 0
        self.lost = 0          # consecutive frames that could not be matched
        self.frames = 0

    @property
    def full(self) -> bool:
        return self.height >= MAX_HEIGHT

    def add(self, img: QImage) -> str:
        """Feed one frame. Returns ``first`` | ``same`` | ``added`` | ``lost``."""
        arr = to_array(img)
        if self.prev is None:
            self.prev, self.height, self.frames = arr, arr.shape[0], 1
            return "first"
        shift = find_shift(self.prev, arr)
        if shift is None:
            self.lost += 1
            return "lost"
        self.lost = 0
        if shift == 0:
            return "same"
        h = arr.shape[0]
        foot = footer_rows(self.prev, arr)
        new_top = self.top + shift
        if self.covered < new_top:                       # rows only the previous frame still shows
            self.parts.append(self.prev[self.covered - self.top:new_top - self.top])
            self.covered = new_top
        end = new_top + h - foot
        if end > self.covered:
            self.parts.append(arr[self.covered - new_top:h - foot])
            self.covered = end
        self.prev, self.top = arr, new_top
        self.height = new_top + h
        self.frames += 1
        return "added"

    def result(self) -> QImage | None:
        if self.prev is None:
            return None
        parts = list(self.parts)
        parts.append(self.prev[self.covered - self.top:])   # rest of the last frame (incl. footer)
        return to_image(np.vstack(parts))
