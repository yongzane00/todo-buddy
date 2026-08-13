from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from todo_buddy.ui.theme import ACCENT, BODY_FONT, DANGER, INK, MUTED, OUTLINE, PAPER


class ActionDialog(QDialog):
    """Reusable themed popup: a title, optional message/content, Cancel + a
    primary action.

    A confirmation ("Delete this quest?") and a picker ("Choose a category
    color") are the same shape — a question and a yes/no-ish decision — so
    both share this one on-theme shell instead of native OS dialogs. Pass a
    `content` widget to turn it into a picker; the caller reads the result
    back off that widget after `exec()` returns Accepted.
    """

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str = "",
        content: QWidget | None = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        danger: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        primary_bg = DANGER if danger else ACCENT
        primary_fg = PAPER if danger else INK
        self.setStyleSheet(f"""
            QDialog {{ background: {PAPER}; }}
            QLabel {{ color: {INK}; font-family: {BODY_FONT}; background: transparent; }}
            QPushButton {{
                background: rgba(255, 253, 248, 235);
                border: 1px solid {OUTLINE};
                border-radius: 6px;
                padding: 6px 18px;
                font-family: {BODY_FONT};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: rgba(212, 165, 78, 90); }}
            QPushButton#primaryButton {{
                background: {primary_bg};
                color: {primary_fg};
            }}
            QPushButton#primaryButton:hover {{ background: {primary_bg}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 700;")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        if message:
            message_label = QLabel(message)
            message_label.setWordWrap(True)
            message_label.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(message_label)

        if content is not None:
            layout.addWidget(content)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton(cancel_text)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        confirm_button = QPushButton(confirm_text)
        confirm_button.setObjectName("primaryButton")
        confirm_button.clicked.connect(self.accept)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

        # A destructive action must never be what a stray Enter key fires;
        # only a non-destructive confirm (a color choice, say) gets to be
        # the button pressing Enter or Return activates.
        if danger:
            cancel_button.setDefault(True)
        else:
            confirm_button.setDefault(True)


def confirm_action(
    parent: QWidget | None,
    title: str,
    message: str,
    confirm_text: str = "Delete",
    danger: bool = True,
) -> bool:
    dialog = ActionDialog(
        parent, title, message=message, confirm_text=confirm_text, danger=danger
    )
    return dialog.exec() == QDialog.DialogCode.Accepted


class ColorSwatchPicker(QWidget):
    """A grid of preset color swatches, plus a fallback to the full OS
    color picker for anyone who wants an exact, non-curated color."""

    PALETTE = [
        "#D4A54E", "#5B78C7", "#D48335", "#7A5EA6",
        "#4E8C8A", "#B85C1E", "#5E7CA6", "#8A9E4E",
        "#A64E7A", "#4E6E4E", "#C97B4E", "#8C4E4E",
    ]

    def __init__(self, current: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.selected_color = current or self.PALETTE[0]
        grid = QGridLayout(self)
        grid.setSpacing(8)
        self._buttons: dict[str, QPushButton] = {}
        columns = 4
        for index, color in enumerate(self.PALETTE):
            swatch = QPushButton()
            swatch.setObjectName(f"swatch-{color}")
            swatch.setToolTip(color)
            swatch.setFixedSize(32, 32)
            swatch.setCheckable(True)
            swatch.setChecked(color.lower() == self.selected_color.lower())
            swatch.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 16px;"
                f" border: 2px solid transparent; padding: 0; }}"
                f"QPushButton:checked {{ border: 2px solid {INK}; }}"
            )
            swatch.clicked.connect(lambda checked=False, c=color: self._select(c))
            self._buttons[color] = swatch
            grid.addWidget(swatch, index // columns, index % columns)

        custom_button = QPushButton("Custom color…")
        custom_button.setObjectName("customColorButton")
        custom_button.clicked.connect(self._pick_custom)
        grid.addWidget(
            custom_button, (len(self.PALETTE) + columns - 1) // columns, 0, 1, columns
        )

    def _select(self, color: str) -> None:
        self.selected_color = color
        for value, button in self._buttons.items():
            button.setChecked(value.lower() == color.lower())

    def _pick_custom(self) -> None:
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Choose a color")
        if color.isValid():
            self._select(color.name())


def choose_color(parent: QWidget | None, title: str, current: str | None) -> str | None:
    picker = ColorSwatchPicker(current)
    dialog = ActionDialog(
        parent, title, content=picker, confirm_text="Apply", cancel_text="Cancel"
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return picker.selected_color
    return None
