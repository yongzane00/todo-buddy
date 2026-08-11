from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from todo_buddy.models import BuddyDocument, Task
from todo_buddy.ui.theme import ACCENT, COMPLETED, INK, OUTLINE, PAPER


TASK_MIME_TYPE = "application/x-todo-buddy-task"


class QuestCheckBox(QCheckBox):
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class TaskRow(QWidget):
    def __init__(self, task_id: str, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self._press_position: QPoint | None = None
        self.setObjectName("taskRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reorder or move to another category")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._press_position is None
            or not event.buttons() & Qt.MouseButton.LeftButton
            or (event.position().toPoint() - self._press_position).manhattanLength()
            < QApplication.startDragDistance()
        ):
            super().mouseMoveEvent(event)
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(TASK_MIME_TYPE, self.task_id.encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_position = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_position = None
        super().mouseReleaseEvent(event)


class _AddQuestEditor(QLineEdit):
    escape_pressed = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        # Popups (including this line edit's own context menu) grab focus;
        # committing then would close the editor under the open menu.
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self.focus_lost.emit()


class AddQuestRow(QWidget):
    """Inline quest entry pinned under a category's tasks.

    The button swaps to a line edit in place: Enter commits (and the editor
    reopens for the next quest), Escape cancels, and clicking elsewhere
    commits whatever non-blank text was typed.
    """

    quest_submitted = Signal(str, str, bool)  # phase_id, title, refocus

    def __init__(self, phase_id: str, phase_title: str, parent=None):
        super().__init__(parent)
        self.phase_id = phase_id
        self._finishing = False
        self.setObjectName(f"add-quest-{phase_id}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 5, 0)
        layout.setSpacing(0)

        self.button = QToolButton()
        self.button.setObjectName("addQuestButton")
        self.button.setText("+ Add quest")
        self.button.setToolTip(f"Add a quest to {phase_title}")
        self.button.setAccessibleName(f"Add quest to {phase_title}")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.button.clicked.connect(self.start_editing)
        layout.addWidget(self.button)

        self.editor = _AddQuestEditor()
        self.editor.setObjectName("addQuestEditor")
        self.editor.setPlaceholderText("New quest, then Enter")
        self.editor.setAccessibleName(f"New quest title for {phase_title}")
        self.editor.hide()
        self.editor.returnPressed.connect(lambda: self._finish(commit=True, refocus=True))
        self.editor.escape_pressed.connect(lambda: self._finish(commit=False, refocus=False))
        self.editor.focus_lost.connect(self._commit_on_blur)
        layout.addWidget(self.editor)

    def start_editing(self) -> None:
        self.button.hide()
        self.editor.clear()
        self.editor.show()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _commit_on_blur(self) -> None:
        if not self._finishing and not self.editor.isHidden():
            self._finish(commit=True, refocus=False)

    def take_pending_text(self) -> str:
        """Close the editor and return any uncommitted, non-blank text.

        Hiding the editor fires focus_lost; the flag stops a double commit.
        """
        if self._finishing or self.editor.isHidden():
            return ""
        self._finishing = True
        try:
            title = self.editor.text().strip()
            self.editor.clear()
            self.editor.hide()
            self.button.show()
            return title
        finally:
            self._finishing = False

    def _finish(self, commit: bool, refocus: bool) -> None:
        # Emit synchronously: this row can be destroyed by the next list
        # rebuild, so it must never own a pending timer. The listening
        # TaskListWidget defers the hand-off past this call stack instead.
        title = self.take_pending_text()
        if commit and title:
            self.quest_submitted.emit(self.phase_id, title, refocus)


class TaskDropArea(QWidget):
    task_dropped = Signal(str, str, int)

    def __init__(self, phase_id: str, parent=None):
        super().__init__(parent)
        self.phase_id = phase_id
        self.rows: list[TaskRow] = []
        self._drop_line_y: int | None = None
        self.setAcceptDrops(True)
        self.setMinimumHeight(36)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 5)
        self._layout.setSpacing(5)

    def set_tasks(
        self,
        tasks: list[Task],
        row_factory: Callable[[Task], TaskRow] | None = None,
    ) -> None:
        self._clear()
        factory = row_factory or (lambda task: TaskRow(task.id))
        for task in tasks:
            row = factory(task)
            self.rows.append(row)
            self._layout.addWidget(row)
        if not tasks:
            placeholder = QLabel("Drop a quest here")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(f"color: {COMPLETED}; font-style: italic; padding: 8px;")
            self._layout.addWidget(placeholder)

    def insertion_index(self, y: int, dragged_task_id: str | None) -> int:
        candidates = [row for row in self.rows if row.task_id != dragged_task_id]
        for index, row in enumerate(candidates):
            if y < row.geometry().center().y():
                return index
        return len(candidates)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(TASK_MIME_TYPE):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        task_id = self._task_id(event.mimeData())
        if task_id is None:
            event.ignore()
            return
        y = int(event.position().y())
        index = self.insertion_index(y, task_id)
        candidates = [row for row in self.rows if row.task_id != task_id]
        if not candidates:
            self._drop_line_y = self.height() // 2
        elif index == 0:
            self._drop_line_y = candidates[0].geometry().top()
        elif index == len(candidates):
            self._drop_line_y = candidates[-1].geometry().bottom()
        else:
            self._drop_line_y = candidates[index].geometry().top()
        self.update()
        self._auto_scroll(event.position().toPoint())
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drop_line()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        task_id = self._task_id(event.mimeData())
        if task_id is None:
            event.ignore()
            return
        index = self.insertion_index(int(event.position().y()), task_id)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self._clear_drop_line()
        QTimer.singleShot(
            0,
            lambda item_id=task_id, phase_id=self.phase_id, target=index:
                self.task_dropped.emit(item_id, phase_id, target),
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_line_y is None:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(ACCENT), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(8, self._drop_line_y, self.width() - 8, self._drop_line_y)

    def _auto_scroll(self, position: QPoint) -> None:
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        if not isinstance(parent, QScrollArea):
            return
        viewport_position = parent.viewport().mapFromGlobal(self.mapToGlobal(position))
        scroll_bar = parent.verticalScrollBar()
        if viewport_position.y() < 32:
            scroll_bar.setValue(scroll_bar.value() - 24)
        elif viewport_position.y() > parent.viewport().height() - 32:
            scroll_bar.setValue(scroll_bar.value() + 24)

    @staticmethod
    def _task_id(mime: QMimeData) -> str | None:
        if not mime.hasFormat(TASK_MIME_TYPE):
            return None
        try:
            value = bytes(mime.data(TASK_MIME_TYPE)).decode("utf-8")
        except UnicodeDecodeError:
            return None
        return value or None

    def _clear_drop_line(self) -> None:
        self._drop_line_y = None
        self.update()

    def _clear(self) -> None:
        self.rows.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach before deleteLater so findChild never returns a
                # widget that is merely awaiting deferred deletion.
                widget.setParent(None)
                widget.deleteLater()


class TaskListWidget(QWidget):
    task_toggled = Signal(str, bool)
    task_add_requested = Signal(str, str, bool)  # phase_id, title, refocus
    task_edit_requested = Signal(str)
    task_delete_requested = Signal(str)
    task_move_requested = Signal(str, str, int)
    phase_edit_requested = Signal(str)
    phase_color_requested = Signal(str)
    phase_delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskList")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(1, 0, 3, 8)
        self._layout.setSpacing(11)

    def set_document(self, document: BuddyDocument) -> None:
        # A rebuild can arrive while an editor still holds typed text (e.g. a
        # mutation that never blurred it). Harvest it so it is not torn down
        # with the old rows, and re-submit it once the new rows exist.
        pending = self._take_pending_quests()
        self._clear()
        if not document.phases:
            empty = QLabel("NO CATEGORIES YET. USE THE MENU TO ADD ONE.")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(empty)

        for phase in document.phases:
            color = phase.color or ACCENT
            section = QWidget()
            section.setObjectName("categorySection")
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(3)
            section_layout.addWidget(self._phase_heading(phase.id, phase.title, color))

            drop_area = TaskDropArea(phase.id)
            drop_area.set_tasks(
                phase.tasks,
                lambda task, category_color=color: self._task_row(task, category_color),
            )
            drop_area.task_dropped.connect(self.task_move_requested)
            section_layout.addWidget(drop_area)

            add_row = AddQuestRow(phase.id, phase.title)
            add_row.quest_submitted.connect(self._relay_quest_submitted)
            section_layout.addWidget(add_row)
            self._layout.addWidget(section)
        self._layout.addStretch(1)

        surviving = {phase.id for phase in document.phases}
        for phase_id, title in pending:
            if phase_id in surviving:
                self._relay_quest_submitted(phase_id, title, False)

    def _relay_quest_submitted(self, phase_id: str, title: str, refocus: bool) -> None:
        # Defer past the emitting row's call stack: the handler rebuilds the
        # list, and this widget (unlike the rows) survives rebuilds, so the
        # timer can never fire on a destroyed emitter.
        QTimer.singleShot(
            0,
            lambda item_id=phase_id, value=title, again=refocus:
                self.task_add_requested.emit(item_id, value, again),
        )

    def start_add_quest(self, phase_id: str) -> None:
        row = self.findChild(AddQuestRow, f"add-quest-{phase_id}")
        if row is not None:
            row.start_editing()

    def flush_pending_quests(self) -> None:
        """Synchronously commit open editors' text (used at app shutdown).

        The normal commit path defers its emission through the event loop,
        which never runs again once the application is quitting.
        """
        for phase_id, title in self._take_pending_quests():
            self.task_add_requested.emit(phase_id, title, False)

    def _take_pending_quests(self) -> list[tuple[str, str]]:
        return [
            (row.phase_id, title)
            for row in self.findChildren(AddQuestRow)
            if (title := row.take_pending_text())
        ]

    def _phase_heading(self, phase_id: str, title: str, color: str) -> QWidget:
        heading = QWidget()
        heading.setObjectName("categoryHeading")
        heading.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QHBoxLayout(heading)
        layout.setContentsMargins(3, 1, 2, 1)
        layout.setSpacing(7)

        color_chip = QLabel()
        color_chip.setFixedSize(7, 24)
        color_chip.setStyleSheet(f"background: {color}; border-radius: 3px;")
        layout.addWidget(color_chip)

        label = QLabel(title)
        label.setObjectName("phaseTitle")
        label.setWordWrap(True)
        layout.addWidget(label, 1)

        menu = QMenu(heading)
        menu.addAction("Edit category...").triggered.connect(
            lambda checked=False, item_id=phase_id: self.phase_edit_requested.emit(item_id)
        )
        menu.addAction("Change color...").triggered.connect(
            lambda checked=False, item_id=phase_id: self.phase_color_requested.emit(item_id)
        )
        menu.addAction("Delete category...").triggered.connect(
            lambda checked=False, item_id=phase_id: self.phase_delete_requested.emit(item_id)
        )
        button = QToolButton()
        button.setObjectName(f"phase-actions-{phase_id}")
        button.setText("...")
        button.setToolTip(f"Actions for {title}")
        button.setAccessibleName(f"Actions for category {title}")
        button.setFixedSize(27, 24)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        layout.addWidget(button)
        return heading

    def _task_row(self, task: Task, color: str) -> TaskRow:
        row = TaskRow(task.id)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 7, 5, 7)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        drag_handle = QLabel("::")
        drag_handle.setToolTip("Drag to reorder")
        drag_handle.setStyleSheet(f"color: {color}; font-weight: 700;")
        drag_handle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(drag_handle)

        checkbox = QuestCheckBox()
        checkbox.setObjectName(f"task-{task.id}")
        checkbox.setAccessibleName(task.title)
        checkbox.setChecked(task.completed)
        checkbox.setFixedWidth(22)
        checkbox.setStyleSheet(
            f"""
            QCheckBox::indicator {{
                width: 17px; height: 17px;
                border: 2px solid {color};
                border-radius: 9px;
                background: {PAPER};
            }}
            QCheckBox::indicator:checked {{
                background: {color};
                image: none;
            }}
            QCheckBox:focus {{ border: 1px dotted {OUTLINE}; }}
            """
        )

        label = QLabel(task.title)
        label.setWordWrap(True)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        font = label.font()
        font.setStrikeOut(task.completed)
        label.setFont(font)
        label.setStyleSheet(f"color: {COMPLETED if task.completed else INK};")

        menu = QMenu(row)
        menu.addAction("Edit quest...").triggered.connect(
            lambda checked=False, task_id=task.id: self.task_edit_requested.emit(task_id)
        )
        menu.addAction("Delete quest...").triggered.connect(
            lambda checked=False, task_id=task.id: self.task_delete_requested.emit(task_id)
        )
        button = QToolButton()
        button.setObjectName(f"task-actions-{task.id}")
        button.setText("...")
        button.setToolTip(f"Actions for {task.title}")
        button.setAccessibleName(f"Actions for quest {task.title}")
        button.setFixedSize(27, 24)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)

        checkbox.toggled.connect(
            lambda checked, task_id=task.id: self.task_toggled.emit(task_id, checked)
        )
        layout.addWidget(checkbox)
        layout.addWidget(label, 1)
        layout.addWidget(button)
        return row

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach before deleteLater so findChild never returns a
                # widget that is merely awaiting deferred deletion.
                widget.setParent(None)
                widget.deleteLater()
