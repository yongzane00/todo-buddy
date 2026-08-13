from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QWidget

from todo_buddy.ui.action_dialog import confirm_action


def prompt_text(parent: QWidget, title: str, label: str, current: str = "") -> str | None:
    value, accepted = QInputDialog.getText(parent, title, label, text=current)
    return value if accepted else None


def confirm_reset(parent: QWidget) -> bool:
    return confirm_action(
        parent,
        "Reset sample data?",
        "Replace all current quests with a fresh sample? A timestamped backup will be kept.",
        confirm_text="Reset",
    )


def confirm_delete(parent: QWidget, title: str, message: str) -> bool:
    return confirm_action(parent, title, message, confirm_text="Delete")
