"""A busy dialog for slow work started from the UI (Take off, fast-forward):
the work runs on a worker thread while a modal progress dialog keeps the
window responsive and shows what is happening.

The game state isn't locked; the dialog is application modal, so nothing in
the UI can change it meanwhile. The simulation already ticks on a background
timer thread and reaches the UI through queued signals, so the work done here
behaves the same way.

Closing the dialog (its X, or Esc) cancels: ``cancelled`` turns True, work
that takes ``should_stop`` ends at its next check, and the caller skips the
steps after it."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, TypeVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

T = TypeVar("T")


class BusyDialog:
    """Runs steps one after another behind one progress dialog."""

    def __init__(self, parent: Optional[QWidget], title: str) -> None:
        self.dialog = QProgressDialog("", "", 0, 0, parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.dialog.setCancelButton(None)  # type: ignore[arg-type]
        self.dialog.setMinimumDuration(0)
        self.dialog.setMinimumWidth(420)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.started = time.monotonic()
        self.cancelled = False
        self._done = False
        self.dialog.canceled.connect(self._cancel)  # type: ignore[attr-defined]

    def _cancel(self) -> None:
        if not self._done:
            self.cancelled = True

    def should_stop(self) -> bool:
        """For the worker: whether the player cancelled."""
        return self.cancelled

    def __enter__(self) -> "BusyDialog":
        self.dialog.show()
        QApplication.processEvents()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._done = True
        self.dialog.close()

    def run(self, text: str, work: Callable[[], T]) -> T:
        """Runs ``work`` on a worker thread, showing ``text``, and returns its
        result (or raises its exception) once it is done."""
        result: list[T] = []
        error: list[BaseException] = []

        def target() -> None:
            try:
                result.append(work())
            except BaseException as ex:  # re-raised on the UI thread
                error.append(ex)

        thread = threading.Thread(target=target, name="busy-work", daemon=True)
        thread.start()
        while thread.is_alive():
            elapsed = int(time.monotonic() - self.started)
            if self.cancelled:
                # Closing hid the dialog; keep it up until the work stops.
                if not self.dialog.isVisible():
                    self.dialog.show()
                label = f"Stopping…\n\n{text}"
            else:
                label = f"{text}\n\n{elapsed // 60}:{elapsed % 60:02d} elapsed"
            self.dialog.setLabelText(label)
            QApplication.processEvents()
            thread.join(0.05)
        QApplication.processEvents()
        if error:
            raise error[0]
        return result[0]
