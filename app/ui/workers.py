"""Background worker infrastructure.

Network requests must never run on the GUI thread. ``Worker`` runs an arbitrary
callable on a ``QThreadPool`` thread and reports back through Qt signals, which
are automatically marshalled to the main thread.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.utils.helpers import friendly_error

logger = logging.getLogger("weathervision.workers")


class WorkerSignals(QObject):
    """Signals emitted by a worker."""
    finished = Signal(object)      # success payload
    error = Signal(str)            # user-friendly error message


class Worker(QRunnable):
    """Runs ``fn(*args, **kwargs)`` on a background thread."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - reported to the GUI
            logger.exception("Worker failed: %s", exc)
            self.signals.error.emit(friendly_error(exc))
        else:
            self.signals.finished.emit(result)
