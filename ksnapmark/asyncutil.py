"""Kleine Hilfe, um blockierende Arbeit (OCR, Upload) im Hintergrund auszuführen."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class _Job(QRunnable):
    def __init__(self, jid: int, fn: Callable[[], Any], signals: _Signals):
        super().__init__()
        self.setAutoDelete(False)
        self.jid = jid
        self.fn = fn
        self.signals = signals

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - Fehler werden an die UI gereicht
            self.signals.failed.emit(self.jid, str(exc))
            return
        self.signals.done.emit(self.jid, result)


class _Hub(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._signals.failed.connect(self._on_failed)
        self._callbacks: dict[int, tuple[Callable, Callable | None]] = {}
        self._jobs: dict[int, _Job] = {}
        self._next = 0

    def submit(self, fn, on_done, on_fail) -> None:
        self._next += 1
        jid = self._next
        job = _Job(jid, fn, self._signals)
        self._jobs[jid] = job
        self._callbacks[jid] = (on_done, on_fail)
        QThreadPool.globalInstance().start(job)

    @Slot(int, object)
    def _on_done(self, jid: int, result: object) -> None:
        self._jobs.pop(jid, None)
        on_done, _ = self._callbacks.pop(jid, (None, None))
        if on_done:
            on_done(result)

    @Slot(int, str)
    def _on_failed(self, jid: int, message: str) -> None:
        self._jobs.pop(jid, None)
        _, on_fail = self._callbacks.pop(jid, (None, None))
        if on_fail:
            on_fail(message)


_hub: _Hub | None = None


def run_async(fn: Callable[[], Any], on_done: Callable[[Any], None],
              on_fail: Callable[[str], None] | None = None) -> None:
    """fn läuft im Thread-Pool, on_done / on_fail im UI-Thread."""
    global _hub
    if _hub is None:
        _hub = _Hub()
    _hub.submit(fn, on_done, on_fail)
