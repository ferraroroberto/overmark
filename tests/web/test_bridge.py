"""A request thread's work runs on the Qt thread; a stuck Qt thread is a timeout, not a hang."""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overmark.web.bridge import BridgeTimeout, QtBridge  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _from_worker(work) -> dict:
    """Run ``work`` on a worker thread while this (Qt) thread serves the event loop."""
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = work()
        except Exception as exc:  # recorded for the assertion, not swallowed
            outcome["error"] = exc

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 5
    while worker.is_alive() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    worker.join(1)
    return outcome


def test_the_call_runs_on_the_qt_thread_and_returns(qapp) -> None:
    bridge = QtBridge()
    main = threading.get_ident()
    outcome = _from_worker(lambda: bridge.call(threading.get_ident))
    assert outcome["value"] == main


def test_an_error_in_the_call_reaches_the_caller(qapp) -> None:
    bridge = QtBridge()

    def fails() -> None:
        raise ValueError("refused")

    outcome = _from_worker(lambda: bridge.call(fails))
    assert isinstance(outcome["error"], ValueError)


def test_no_event_loop_means_a_timeout(qapp) -> None:
    bridge = QtBridge()
    with pytest.raises(BridgeTimeout, match="did not answer"):
        bridge.call(lambda: 1, timeout=0.05)  # this thread is waiting, so nothing runs it
