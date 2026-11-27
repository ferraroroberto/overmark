"""Hand a web request's work to the Qt thread and wait for its answer.

The settings server runs on its own thread, but hotkeys, overlays and windows belong to
the Qt thread: only it may apply a save. ``QtBridge.call`` queues a function onto the Qt
event loop and blocks the request until it has run there.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, TypeVar

from PySide6.QtCore import QObject, Qt, Signal

log = logging.getLogger(__name__)

T = TypeVar("T")

CALL_TIMEOUT_S = 15.0  # a save applies in milliseconds; past this the Qt thread is stuck


class BridgeTimeout(TimeoutError):
    """The Qt thread did not run the call in time; the server answers it with a 503."""


class QtBridge(QObject):
    """Create on the Qt thread; ``call`` from any other thread."""

    _queued = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._queued.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, job: tuple[Callable[[], Any], Future]) -> None:
        work, future = job
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(work())
        except BaseException as exc:  # handed back to the waiting request, not swallowed
            future.set_exception(exc)

    def call(self, work: Callable[[], T], timeout: float = CALL_TIMEOUT_S) -> T:
        """Run ``work`` on the Qt thread and return its result (or raise its error)."""
        future: Future = Future()
        self._queued.emit((work, future))
        try:
            return future.result(timeout)
        except FutureTimeout:
            future.cancel()
            log.warning("⚠️ the Qt thread did not answer a settings request in %ss", timeout)
            raise BridgeTimeout(f"the app did not answer within {timeout:g} s") from None
