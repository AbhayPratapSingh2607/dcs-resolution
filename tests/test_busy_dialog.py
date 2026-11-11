"""Closing the Take off / Fast-forward busy dialog cancels the work."""

import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from qt_ui.widgets.busy import BusyDialog  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else QApplication([])


def test_closing_the_dialog_stops_the_work(app: QApplication) -> None:
    ticks: list[int] = []

    def work(should_stop) -> bool:  # type: ignore[no-untyped-def]
        # Like the fast forward: tick until done or told to stop.
        for i in range(200):
            if should_stop():
                return False
            ticks.append(i)
            time.sleep(0.01)
        return True

    with BusyDialog(None, "Take off") as busy:
        QTimer.singleShot(100, busy.dialog.close)  # the player clicks the X
        finished = busy.run("Fighting…", lambda: work(busy.should_stop))
    assert busy.cancelled
    assert finished is False
    assert len(ticks) < 200


def test_finishing_normally_is_not_a_cancel(app: QApplication) -> None:
    done = threading.Event()
    with BusyDialog(None, "Take off") as busy:
        busy.run("Generating…", done.set)
    assert done.is_set()
    # The dialog closing itself at the end doesn't count as a cancel.
    assert not busy.cancelled


def test_a_dialog_that_cannot_be_cancelled_ignores_the_close(app: QApplication) -> None:
    # Processing a turn's results must not stop halfway.
    with BusyDialog(None, "End of mission", cancellable=False) as busy:
        QTimer.singleShot(50, busy.dialog.close)
        busy.run("Processing…", lambda: time.sleep(0.3))
        assert busy.dialog.isVisible()
    assert not busy.cancelled
