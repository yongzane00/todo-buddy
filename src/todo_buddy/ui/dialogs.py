from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from todo_buddy.models import Phase


def prompt_text(parent: QWidget, title: str, label: str, current: str = "") -> str | None:
    value, accepted = QInputDialog.getText(parent, title, label, text=current)
    return value if accepted else None


def choose_phase(parent: QWidget, phases: list[Phase]) -> str | None:
    if not phases:
        QMessageBox.information(parent, "Add quest", "Add a category before adding a quest.")
        return None
    if len(phases) == 1:
        return phases[0].id
    labels = [phase.title for phase in phases]
    selected, accepted = QInputDialog.getItem(
        parent, "Choose category", "Add the quest to:", labels, editable=False
    )
    if not accepted:
        return None
    return phases[labels.index(selected)].id


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
