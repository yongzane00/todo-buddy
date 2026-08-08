from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from todo_buddy.service import TaskService
from todo_buddy.ui.card_widget import CardWidget, FooterWidget, TriangleTrim
from todo_buddy.ui.cat_widget import CatWidget
from todo_buddy.ui.dialogs import confirm_delete, confirm_reset, prompt_text
from todo_buddy.ui.task_list_widget import TaskListWidget
from todo_buddy.ui.theme import INK, MUTED, OUTLINE, application_stylesheet


CARD_WIDTH = 380
CARD_HEIGHT = 680
MINI_WIDTH = 76
MINI_HEIGHT = 70


def clamp_position(
    position: QPoint, width: int, height: int, available_geometries: Sequence[QRect]
) -> QPoint:
    if not available_geometries:
        return position

    containing = next((area for area in available_geometries if area.contains(position)), None)
    if containing is None:
        def distance(area: QRect) -> int:
            x = min(max(position.x(), area.left()), area.right())
            y = min(max(position.y(), area.top()), area.bottom())
            return (position.x() - x) ** 2 + (position.y() - y) ** 2

        containing = min(available_geometries, key=distance)

    max_x = max(containing.left(), containing.right() - width + 1)
    max_y = max(containing.top(), containing.bottom() - height + 1)
    return QPoint(
        min(max(position.x(), containing.left()), max_x),
        min(max(position.y(), containing.top()), max_y),
    )


class DragHeader(QWidget):
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self._press_position: QPoint | None = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_position = event.globalPosition().toPoint()
            self._drag_offset = global_position - self.window().frameGeometry().topLeft()
            self._press_position = global_position
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        global_position = event.globalPosition().toPoint()
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (
                not self._dragging
                and self._press_position is not None
                and (global_position - self._press_position).manhattanLength()
                >= QApplication.startDragDistance()
            ):
                self._dragging = True
                self.drag_started.emit()
            if self._dragging:
                self.window().move(global_position - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self.drag_finished.emit()
        self._drag_offset = None
        self._press_position = None
        self._dragging = False
        super().mouseReleaseEvent(event)


class MiniCatPage(QWidget):
    """Hosts just the cat while the card is minimized.

    A plain click restores the full card; a drag moves the window instead,
    so releasing after a drag never triggers a restore.
    """

    clicked = Signal()
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self._press_position: QPoint | None = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to reopen Todo Buddy. Drag to move the cat.")
        self.setAccessibleName("Reopen Todo Buddy")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(0)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_position = event.globalPosition().toPoint()
            self._drag_offset = global_position - self.window().frameGeometry().topLeft()
            self._press_position = global_position
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        global_position = event.globalPosition().toPoint()
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (
                not self._dragging
                and self._press_position is not None
                and (global_position - self._press_position).manhattanLength()
                >= QApplication.startDragDistance()
            ):
                self._dragging = True
                self.drag_started.emit()
            if self._dragging:
                self.window().move(global_position - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        was_dragging = self._dragging
        was_pressed = self._press_position is not None
        self._drag_offset = None
        self._press_position = None
        self._dragging = False
        if was_dragging:
            self.drag_finished.emit()
        elif was_pressed and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: TaskService,
        settings: QSettings | None = None,
        restore_position: bool = True,
    ):
        super().__init__()
        self.service = service
        self.settings = settings or QSettings("TodoBuddy", "TodoBuddy")
        self._persist_position = restore_position
        self.tray_icon: QSystemTrayIcon | None = None
        self._cat_minimized = False
        self._cat_center_offset: QPoint | None = None
        self._cat_layout_index = -1
        self.setWindowTitle("Todo Buddy")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setStyleSheet(application_stylesheet())
        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._setup_tray()
        self._render()
        if restore_position:
            self._restore_position()

    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        card = CardWidget()
        self.card = card
        self.stack.addWidget(card)
        self.mini_page = MiniCatPage()
        self.mini_page.clicked.connect(self._restore_from_cat)
        self.mini_page.drag_started.connect(self._cat_angry)
        self.mini_page.drag_finished.connect(self._cat_calm)
        self.stack.addWidget(self.mini_page)
        root = QVBoxLayout(card)
        self._card_layout = root
        root.setContentsMargins(16, 13, 16, 13)
        root.setSpacing(6)

        header = DragHeader()
        header.setFixedHeight(56)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 1, 0)
        header_layout.setSpacing(3)
        self.title_label = QLabel()
        self.title_label.setObjectName("projectTitle")
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.title_label.setWordWrap(True)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self.title_label, 1)
        header.drag_started.connect(self._cat_angry)
        header.drag_finished.connect(self._cat_calm)

        minimize_button = QToolButton()
        minimize_button.setObjectName("minimizeButton")
        minimize_button.setText("_")
        minimize_button.setToolTip("Minimize to just the cat")
        minimize_button.setAccessibleName("Minimize Todo Buddy")
        minimize_button.setFixedSize(24, 24)
        minimize_button.clicked.connect(self._minimize)
        header_layout.addWidget(minimize_button)

        menu_button = QToolButton()
        menu_button.setObjectName("menuButton")
        menu_button.setText("...")
        menu_button.setToolTip("Quest menu")
        menu_button.setAccessibleName("Quest menu")
        menu_button.setFixedSize(27, 24)
        menu_button.clicked.connect(self._show_menu)
        header_layout.addWidget(menu_button)

        close_button = QToolButton()
        close_button.setObjectName("closeButton")
        close_button.setText("X")
        close_button.setToolTip("Exit Todo Buddy")
        close_button.setAccessibleName("Exit Todo Buddy")
        close_button.setFixedSize(24, 24)
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)
        root.addWidget(header)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"border: none; border-top: 2px dashed {OUTLINE};")
        root.addWidget(separator)

        summary = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("font-weight: 700;")
        summary.addWidget(self.progress_bar, 1)
        summary.addWidget(self.progress_label)
        root.addLayout(summary)

        self.next_label = QLabel()
        self.next_label.setObjectName("nextTask")
        self.next_label.setWordWrap(True)
        root.addWidget(self.next_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        self.task_list = TaskListWidget()
        self.task_list.task_toggled.connect(self._set_task_completion)
        self.task_list.task_add_requested.connect(self._add_task_inline)
        self.task_list.task_edit_requested.connect(self._edit_task)
        self.task_list.task_delete_requested.connect(self._delete_task)
        self.task_list.task_move_requested.connect(self._move_task)
        self.task_list.phase_edit_requested.connect(self._edit_phase)
        self.task_list.phase_color_requested.connect(self._change_phase_color)
        self.task_list.phase_delete_requested.connect(self._delete_phase)
        scroll.setWidget(self.task_list)
        root.addWidget(scroll, 1)

        self.cat = CatWidget()
        root.addWidget(self.cat)
        root.addWidget(TriangleTrim())
        footer = FooterWidget()
        footer.setFixedHeight(41)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 3, 12, 3)
        dots = QLabel("*  *  *")
        dots.setStyleSheet(f"color: {INK}; font-size: 8px;")
        self.footer_label = QLabel()
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.footer_label.setStyleSheet("font-weight: 700; letter-spacing: 1px;")
        footer_layout.addWidget(dots)
        footer_layout.addWidget(self.footer_label, 1)
        root.addWidget(footer)

    def _render(self) -> None:
        self.title_label.setText(self.service.document.title)
        completed, total = self.service.progress()
        self.progress_label.setText(f"{completed} / {total}")
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(completed)
        next_task = self.service.next_incomplete_task()
        if next_task is None:
            self.next_label.setText("ALL QUESTS COMPLETE.")
            self.next_label.setStyleSheet(f"color: {MUTED}; font-weight: 700;")
        else:
            self.next_label.setText(f"NEXT: {next_task.title}")
            self.next_label.setStyleSheet(f"color: {MUTED};")
        noun = "QUEST" if total == 1 else "QUESTS"
        self.footer_label.setText(f"{completed}/{total} {noun}")
        self.task_list.set_document(self.service.document)

    def _set_task_completion(self, task_id: str, completed: bool) -> None:
        try:
            self.service.set_task_completion(task_id, completed)
        except Exception as error:
            self._show_error("Could not update quest", error)
        else:
            if completed:
                self.cat.celebrate()
            else:
                self.cat.note_activity()
        self._render()

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Add category...", self._add_phase)
        menu.addAction("Rename card...", self._rename)
        menu.addSeparator()
        completed, total = self.service.progress()
        mark_all = menu.addAction("Mark all complete", self._mark_all_complete)
        mark_all.setEnabled(total > 0 and completed < total)
        mark_none = menu.addAction("Mark all incomplete", self._mark_all_incomplete)
        mark_none.setEnabled(completed > 0)
        clear_completed = menu.addAction("Delete completed quests...", self._delete_completed)
        clear_completed.setEnabled(completed > 0)
        menu.addSeparator()
        menu.addAction("Minimize", self._minimize)
        menu.addAction("Open data folder", self._open_data_folder)
        menu.addAction("Reset sample data...", self._reset_sample)
        menu.addSeparator()
        menu.addAction("Exit", self.close)
        button = self.findChild(QToolButton, "menuButton")
        menu.exec(button.mapToGlobal(button.rect().bottomRight()))

    def _add_task_inline(self, phase_id: str, title: str, refocus: bool) -> None:
        added = self._mutate(
            lambda: self.service.add_task(phase_id, title), "Could not add quest"
        )
        if added and refocus:
            # Enter commits and reopens the editor for rapid quest entry.
            self.task_list.start_add_quest(phase_id)

    def _add_phase(self) -> None:
        title = prompt_text(self, "Add category", "Category name:")
        if title is not None:
            self._mutate(lambda: self.service.add_phase(title), "Could not add category")

    def _edit_task(self, task_id: str) -> None:
        task = next(
            (task for phase in self.service.document.phases for task in phase.tasks if task.id == task_id),
            None,
        )
        if task is None:
            return
        title = prompt_text(self, "Edit quest", "Quest title:", task.title)
        if title is not None:
            self._mutate(
                lambda: self.service.rename_task(task_id, title), "Could not edit quest"
            )

    def _delete_task(self, task_id: str) -> None:
        task = next(
            (task for phase in self.service.document.phases for task in phase.tasks if task.id == task_id),
            None,
        )
        if task is None or not confirm_delete(
            self, "Delete quest?", f'Delete "{task.title}"? This cannot be undone.'
        ):
            return
        self._mutate(lambda: self.service.delete_task(task_id), "Could not delete quest")

    def _edit_phase(self, phase_id: str) -> None:
        phase = next(
            (phase for phase in self.service.document.phases if phase.id == phase_id), None
        )
        if phase is None:
            return
        title = prompt_text(self, "Edit category", "Category name:", phase.title)
        if title is not None:
            self._mutate(
                lambda: self.service.rename_phase(phase_id, title), "Could not edit category"
            )

    def _change_phase_color(self, phase_id: str) -> None:
        phase = next(
            (phase for phase in self.service.document.phases if phase.id == phase_id), None
        )
        if phase is None:
            return
        color = QColorDialog.getColor(
            QColor(phase.color or "#D4A54E"), self, "Choose category color"
        )
        if color.isValid():
            self._mutate(
                lambda: self.service.set_phase_color(phase_id, color.name()),
                "Could not change category color",
            )

    def _delete_phase(self, phase_id: str) -> None:
        phase = next(
            (phase for phase in self.service.document.phases if phase.id == phase_id), None
        )
        if phase is None:
            return
        task_count = len(phase.tasks)
        noun = "quest" if task_count == 1 else "quests"
        message = (
            f'Delete "{phase.title}" and its {task_count} {noun}? This cannot be undone.'
        )
        if not confirm_delete(self, "Delete category?", message):
            return
        self._mutate(
            lambda: self.service.delete_phase(phase_id), "Could not delete category"
        )

    def _move_task(self, task_id: str, phase_id: str, index: int) -> None:
        if self._mutate(
            lambda: self.service.move_task(task_id, phase_id, index),
            "Could not move quest",
        ):
            self.cat.note_activity()

    def _mark_all_complete(self) -> None:
        if self._mutate(
            lambda: self.service.set_all_tasks_completion(True),
            "Could not complete all quests",
        ):
            self.cat.celebrate()

    def _mark_all_incomplete(self) -> None:
        self._mutate(
            lambda: self.service.set_all_tasks_completion(False),
            "Could not reopen all quests",
        )

    def _delete_completed(self) -> None:
        completed, _ = self.service.progress()
        noun = "quest" if completed == 1 else "quests"
        if not confirm_delete(
            self,
            "Delete completed quests?",
            f"Permanently delete {completed} completed {noun}?",
        ):
            return
        self._mutate(self.service.delete_completed_tasks, "Could not delete completed quests")

    def _rename(self) -> None:
        title = prompt_text(self, "Rename card", "Project title:", self.service.document.title)
        if title is not None:
            self._mutate(lambda: self.service.rename_document(title), "Could not rename card")

    def _reset_sample(self) -> None:
        if confirm_reset(self):
            self._mutate(self.service.reset_sample_data, "Could not reset task data")

    def _mutate(self, operation, message: str) -> bool:
        try:
            operation()
        except Exception as error:
            self._show_error(message, error)
            succeeded = False
        else:
            succeeded = True
        self._render()
        return succeeded

    def _open_data_folder(self) -> None:
        path = getattr(self.service.repository, "path", None)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        except OSError as error:
            self._show_error("Could not open the data folder", error)

    def _show_error(self, title: str, error: Exception) -> None:
        box = QMessageBox(QMessageBox.Icon.Critical, title, str(error), parent=self)
        box.setInformativeText("No task data was discarded. Check the data file and try again.")
        box.exec()

    def _cat_angry(self) -> None:
        self.cat.start_angry()

    def _cat_calm(self) -> None:
        self.cat.stop_angry()

    def eventFilter(self, watched, event) -> bool:
        if (
            isinstance(watched, QWidget)
            and (watched is self or self.isAncestorOf(watched))
            and event.type()
            in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.KeyPress,
                QEvent.Type.Wheel,
                QEvent.Type.TouchBegin,
            )
        ):
            self.cat.note_activity()
        return super().eventFilter(watched, event)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self.tray_icon.setToolTip("Todo Buddy")
        tray_menu = QMenu()
        tray_menu.addAction("Show Todo Buddy", self._restore_from_tray)
        tray_menu.addAction("Exit", self.close)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _minimize(self) -> None:
        """Collapse the card so only the animated cat stays on the desktop."""
        if self._cat_minimized:
            return
        self._cat_minimized = True
        self._cat_layout_index = self._card_layout.indexOf(self.cat)
        self._cat_center_offset = self.cat.mapTo(
            self, QPoint(self.cat.width() // 2, self.cat.height() // 2)
        )
        cat_center = self.pos() + self._cat_center_offset
        self.mini_page.layout().addWidget(self.cat)
        self.stack.setCurrentWidget(self.mini_page)
        self.setFixedSize(MINI_WIDTH, MINI_HEIGHT)
        # Keep the cat where it was on screen while the card vanishes.
        target = cat_center - QPoint(MINI_WIDTH // 2, MINI_HEIGHT // 2)
        self.move(clamp_position(target, MINI_WIDTH, MINI_HEIGHT, self._screen_geometries()))

    def _restore_from_cat(self) -> None:
        if not self._cat_minimized:
            return
        target = self._expanded_position()
        self._cat_minimized = False
        self._card_layout.insertWidget(self._cat_layout_index, self.cat)
        self.stack.setCurrentWidget(self.card)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.move(clamp_position(target, CARD_WIDTH, CARD_HEIGHT, self._screen_geometries()))
        self.raise_()
        self.activateWindow()

    def _expanded_position(self) -> QPoint:
        """Top-left of the full card such that the cat stays where it is now."""
        if not self._cat_minimized or self._cat_center_offset is None:
            return self.pos()
        mini_center = self.pos() + QPoint(MINI_WIDTH // 2, MINI_HEIGHT // 2)
        return mini_center - self._cat_center_offset

    def _screen_geometries(self) -> list[QRect]:
        app = QApplication.instance()
        return [screen.availableGeometry() for screen in app.screens()] if app else []

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        if self._cat_minimized:
            self._restore_from_cat()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _restore_position(self) -> None:
        screens = self._screen_geometries()
        saved = self.settings.value("window/position")
        if isinstance(saved, QPoint):
            target = saved
        elif screens:
            primary = screens[0]
            target = QPoint(primary.right() - self.width() - 23, primary.top() + 24)
        else:
            return
        self.move(clamp_position(target, self.width(), self.height(), screens))

    def closeEvent(self, event: QCloseEvent) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if self._persist_position:
            # While minimized to the cat, save where the full card would sit
            # so the next launch reopens the card, not a stray corner.
            self.settings.setValue("window/position", self._expanded_position())
            self.settings.sync()
        super().closeEvent(event)
        # quitOnLastWindowClosed only reacts to visible windows, so closing
        # from the tray menu while the card is hidden would leave the process
        # running. Quit explicitly; this is a no-op when no event loop runs.
        if event.isAccepted() and app is not None:
            app.quit()
