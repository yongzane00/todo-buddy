from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget


def prompt_text(parent: QWidget, title: str, label: str, current: str = "") -> str | None:
    value, accepted = QInputDialog.getText(parent, title, label, text=current)
    return value if accepted else None


def confirm_reset(parent: QWidget) -> bool:
    result = QMessageBox.question(
        parent,
        "Reset sample data?",
        "Replace all current quests with a fresh sample? A timestamped backup will be kept.",
        QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return result == QMessageBox.StandardButton.Reset


def confirm_delete(parent: QWidget, title: str, message: str) -> bool:
    result = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return result == QMessageBox.StandardButton.Yes
