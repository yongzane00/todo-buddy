from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from todo_buddy.paths import migrate_legacy_data, resolve_data_path
from todo_buddy.repository import JsonRepository, RepositoryError
from todo_buddy.sample_data import create_sample_document
from todo_buddy.service import TaskService
from todo_buddy.ui.main_window import MainWindow
from todo_buddy.ui.theme import application_stylesheet


def _load_service(repository: JsonRepository) -> TaskService | None:
    service = TaskService(repository)
    try:
        service.load_or_initialize()
        return service
    except RepositoryError as error:
        response = QMessageBox.warning(
            None,
            "Todo Buddy data needs attention",
            f"{error}\n\nRecover with fresh sample data? The current file will be backed up first.",
            QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Reset:
            return None
        try:
            repository.backup()
            repository.save(create_sample_document())
            service.load_or_initialize()
            return service
        except RepositoryError as recovery_error:
            QMessageBox.critical(None, "Recovery failed", str(recovery_error))
            return None


def _install_interrupt_handling(app: QApplication, window: MainWindow) -> QTimer:
    """Make Ctrl+C (and console close/terminate signals) exit promptly.

    Python only delivers console signals while the interpreter is executing
    bytecode, and Qt's exec() blocks inside C++. Without the periodic wake-up
    timer a Ctrl+C would wait for the next Python slot to run (up to the 20 s
    cat inactivity timer) and the KeyboardInterrupt raised there would be
    swallowed at the slot boundary, leaving the app running. Routing the
    signal to window.close() instead exits cleanly through closeEvent, which
    also persists the window position.
    """

    def request_exit(*_):
        window.close()

    signal.signal(signal.SIGINT, request_exit)
    signal.signal(signal.SIGTERM, request_exit)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_exit)

    wake = QTimer(app)
    wake.setInterval(150)
    wake.timeout.connect(lambda: None)
    wake.start()
    return wake


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("TodoBuddy")
    app.setApplicationName("Todo Buddy")
    app.setApplicationVersion("0.1.0")
    app.setQuitOnLastWindowClosed(True)
    app.setStyleSheet(application_stylesheet())

    data_path = resolve_data_path()
    migrate_legacy_data(data_path)
    repository = JsonRepository(data_path, create_sample_document)
    service = _load_service(repository)
    if service is None:
        return 1

    window = MainWindow(service)
    window.show()
    _install_interrupt_handling(app, window)
    return app.exec()
