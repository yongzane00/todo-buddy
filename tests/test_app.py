import os
import signal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from todo_companion.app import _install_interrupt_handling
from todo_companion.models import CompanionDocument, Phase, SyncMetadata, Task
from todo_companion.service import TaskService
from todo_companion.ui.main_window import MainWindow


class MemoryRepository:
    def __init__(self):
        self.document = CompanionDocument(
            schema_version=1,
            title="APP TEST QUEST",
            phases=[Phase(id="phase", title="PHASE 1: TEST", tasks=[Task(id="task", title="Toggle me")])],
            sync=SyncMetadata(),
        )

    def load(self):
        return CompanionDocument.from_dict(self.document.to_dict())

    def save(self, document):
        self.document = CompanionDocument.from_dict(document.to_dict())

    def backup(self):
        return None


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def service():
    value = TaskService(MemoryRepository())
    value.load_or_initialize()
    return value


def test_interrupt_handling_routes_console_signals_to_window_close(app):
    window = MainWindow(service(), restore_position=False)
    window.show()
    previous = {signal.SIGINT: signal.getsignal(signal.SIGINT), signal.SIGTERM: signal.getsignal(signal.SIGTERM)}
    wake = _install_interrupt_handling(app, window)
    try:
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        assert handler is signal.getsignal(signal.SIGTERM)
        assert wake.isActive()

        handler()

        assert not window.isVisible()
    finally:
        wake.stop()
        for signum, old in previous.items():
            signal.signal(signum, old)


def test_close_while_hidden_quits_event_loop(app):
    window = MainWindow(service(), restore_position=False)
    window.show()
    window.hide()  # minimized to tray

    QTimer.singleShot(0, window.close)  # tray menu "Exit"
    safety = QTimer()
    safety.setSingleShot(True)
    safety.timeout.connect(lambda: app.exit(99))
    safety.start(2_000)

    assert app.exec() == 0
    safety.stop()
