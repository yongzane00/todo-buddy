import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QDropEvent, QFocusEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton, QToolButton, QWidget

from todo_buddy.models import BuddyDocument, Phase, SyncMetadata, Task
from todo_buddy.service import TaskService
from todo_buddy.ui import action_dialog, dialogs
from todo_buddy.ui import main_window as main_window_module
from todo_buddy.ui.action_dialog import ColorSwatchPicker, choose_color
from todo_buddy.ui.main_window import (
    CARD_HEIGHT,
    CARD_WIDTH,
    MINI_HEIGHT,
    MINI_WIDTH,
    MainWindow,
    clamp_position,
)
from todo_buddy.ui.cat_widget import CatState, CatWidget
from todo_buddy.ui.task_list_widget import (
    TASK_MIME_TYPE,
    AddQuestRow,
    QuestCheckBox,
    TaskDropArea,
    TaskListWidget,
    TaskRow,
)


class MemoryRepository:
    def __init__(self):
        self.document = BuddyDocument(
            schema_version=1,
            title="UI TEST QUEST",
            phases=[Phase(id="phase", title="PHASE 1: TEST", tasks=[Task(id="task", title="Toggle me")])],
            sync=SyncMetadata(),
        )
        self.save_count = 0

    def load(self):
        return BuddyDocument.from_dict(self.document.to_dict())

    def save(self, document):
        self.save_count += 1
        self.document = BuddyDocument.from_dict(document.to_dict())

    def backup(self):
        return None


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def service():
    repository = MemoryRepository()
    value = TaskService(repository)
    value.load_or_initialize()
    return value, repository


def test_main_window_uses_floating_window_flags_and_transparency(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.windowFlags() & Qt.WindowType.Tool
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.close()


def test_task_list_emits_task_id_and_new_state(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    changes = []
    widget.task_toggled.connect(lambda task_id, checked: changes.append((task_id, checked)))

    checkbox = widget.findChild(QuestCheckBox, "task-task")
    checkbox.click()

    assert changes == [("task", True)]
    assert checkbox.isChecked()


def test_task_and_phase_menus_are_delete_only(app):
    # Edit moved to double-click and color moved to the chip, so the "..."
    # dropdown for each line item is left with just its delete action.
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    requested = []
    widget.task_delete_requested.connect(lambda item_id: requested.append(("delete-task", item_id)))
    widget.phase_delete_requested.connect(lambda item_id: requested.append(("delete-phase", item_id)))

    task_menu = widget.findChild(QToolButton, "task-actions-task").menu()
    phase_menu = widget.findChild(QToolButton, "phase-actions-phase").menu()

    assert [action.text() for action in task_menu.actions()] == ["Delete quest..."]
    assert [action.text() for action in phase_menu.actions()] == ["Delete category..."]

    task_menu.actions()[0].trigger()
    phase_menu.actions()[0].trigger()

    assert requested == [("delete-task", "task"), ("delete-phase", "phase")]


def test_color_chip_click_emits_phase_color_requested(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    requested = []
    widget.phase_color_requested.connect(requested.append)

    widget.findChild(QPushButton, "phase-color-phase").click()

    assert requested == ["phase"]


def test_task_row_has_no_drag_hint_tooltip(app):
    # The dark "Drag to reorder..." hover box was intentionally removed.
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)

    assert widget.findChild(TaskRow, "taskRow").toolTip() == ""


def test_double_click_task_row_opens_inline_editor_and_renames(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    renamed = []
    widget.task_rename_requested.connect(lambda task_id, title: renamed.append((task_id, title)))
    row = widget.findChild(TaskRow, "taskRow")
    editor = row.findChild(QLineEdit, "taskTitleEditor")
    assert editor.isHidden()  # sanity: editor starts hidden

    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)

    assert not editor.isHidden()
    assert editor.text() == "Toggle me"  # pre-filled and pre-selected

    QTest.keyClicks(editor, "Renamed quest")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()  # the rename relay defers emission by one event-loop turn

    assert renamed == [("task", "Renamed quest")]
    assert editor.isHidden()


def test_double_click_task_row_escape_cancels_without_emitting(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    renamed = []
    widget.task_rename_requested.connect(lambda task_id, title: renamed.append((task_id, title)))
    row = widget.findChild(TaskRow, "taskRow")

    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
    editor = row.findChild(QLineEdit, "taskTitleEditor")
    QTest.keyClicks(editor, "Ignored edit")
    QTest.keyClick(editor, Qt.Key.Key_Escape)

    assert renamed == []
    assert editor.isHidden()


def test_double_click_phase_heading_renames_inline(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    renamed = []
    widget.phase_rename_requested.connect(lambda phase_id, title: renamed.append((phase_id, title)))
    heading = widget.findChild(QWidget, "categoryHeading")

    QTest.mouseDClick(heading, Qt.MouseButton.LeftButton)
    editor = heading.findChild(QLineEdit, "phaseTitleEditor")
    assert editor.text() == "PHASE 1: TEST"

    QTest.keyClicks(editor, "Renamed category")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()  # the rename relay defers emission by one event-loop turn

    assert renamed == [("phase", "Renamed category")]


def test_drop_area_calculates_post_removal_insertion_indexes(app):
    tasks = [Task(id="a", title="A"), Task(id="b", title="B"), Task(id="c", title="C")]
    area = TaskDropArea("phase")
    area.set_tasks(tasks)
    area.resize(300, area.sizeHint().height())
    area.show()
    app.processEvents()

    assert area.insertion_index(-10, "a") == 0
    assert area.insertion_index(10_000, "a") == 2
    assert area.insertion_index(10_000, None) == 3


def test_drop_area_emits_persistable_move_intent(app):
    area = TaskDropArea("destination")
    area.set_tasks([Task(id="existing", title="Existing")])
    moves = []
    area.task_dropped.connect(
        lambda task_id, phase_id, index: moves.append((task_id, phase_id, index))
    )
    mime = QMimeData()
    mime.setData(TASK_MIME_TYPE, b"moving")
    event = QDropEvent(
        QPointF(5, 10_000),
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    area.dropEvent(event)
    app.processEvents()

    assert event.isAccepted()
    assert moves == [("moving", "destination", 1)]


def test_cat_state_transitions_are_explicit(app):
    cat = CatWidget(inactivity_ms=60_000)

    assert cat.state == CatState.AWAKE
    cat.fall_asleep()
    assert cat.state == CatState.SLEEPING
    cat.note_activity()
    assert cat.state == CatState.WAKING
    for _ in range(6):  # the one-shot wake-up sheet returns to AWAKE on wrap
        cat._advance_frame()
    assert cat.state == CatState.AWAKE
    cat.celebrate()
    assert cat.state == CatState.HAPPY
    cat.start_angry()
    assert cat.state == CatState.ANGRY
    cat.stop_angry()
    assert cat.state == CatState.AWAKE


def test_cat_loads_a_sprite_sheet_for_every_state(app):
    cat = CatWidget()

    assert set(cat._sheets) == set(CatState)
    for state in CatState:
        cat._set_state(state)
        assert cat._frame_count() == 6


def test_main_window_toggle_persists_and_updates_progress(app):
    task_service, repository = service()
    window = MainWindow(task_service, restore_position=False)

    window.findChild(QuestCheckBox, "task-task").click()

    assert repository.save_count == 1
    assert window.progress_label.text() == "1 / 1"
    assert window.progress_bar.value() == 1
    assert window.cat.state == CatState.HAPPY
    window.close()


def test_main_window_has_minimize_control(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)

    button = window.findChild(QToolButton, "minimizeButton")

    assert button is not None
    assert button.accessibleName() == "Minimize Todo Buddy"
    window.close()


def test_minimize_collapses_to_cat_and_click_restores_in_place(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    window.show()
    app.processEvents()
    area = QApplication.primaryScreen().availableGeometry()
    origin = QPoint(area.left() + 50, area.top())
    window.move(origin)

    window.findChild(QToolButton, "minimizeButton").click()

    assert window.stack.currentWidget() is window.mini_page
    assert window.cat.parent() is window.mini_page
    assert (window.width(), window.height()) == (MINI_WIDTH, MINI_HEIGHT)

    QTest.mouseClick(window.mini_page, Qt.MouseButton.LeftButton)

    assert window.stack.currentWidget() is window.card
    assert window.card.isAncestorOf(window.cat)
    assert (window.width(), window.height()) == (CARD_WIDTH, CARD_HEIGHT)
    assert window.pos() == origin
    window.close()


def test_restore_from_tray_also_exits_cat_mode(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    window.show()
    app.processEvents()

    window._minimize()
    assert window.stack.currentWidget() is window.mini_page

    window._restore_from_tray()

    assert window.stack.currentWidget() is window.card
    assert (window.width(), window.height()) == (CARD_WIDTH, CARD_HEIGHT)
    window.close()


def test_close_while_cat_minimized_saves_expanded_card_position(app, tmp_path):
    task_service, _ = service()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(task_service, settings=settings, restore_position=True)
    window.show()
    app.processEvents()
    area = QApplication.primaryScreen().availableGeometry()
    origin = QPoint(area.left() + 40, area.top())
    window.move(origin)

    window._minimize()
    assert window.pos() != origin  # the mini window sits where the cat was
    window.close()

    assert settings.value("window/position") == origin


def test_add_quest_row_commits_on_enter_and_cancels_on_escape(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    submitted = []
    widget.task_add_requested.connect(
        lambda phase_id, title, refocus: submitted.append((phase_id, title, refocus))
    )
    row = widget.findChild(AddQuestRow, "add-quest-phase")

    row.button.click()
    assert row.button.isHidden()
    assert not row.editor.isHidden()

    row.editor.setText("  Feed Kumquat  ")
    QTest.keyClick(row.editor, Qt.Key.Key_Return)
    app.processEvents()

    assert submitted == [("phase", "Feed Kumquat", True)]
    assert row.editor.isHidden()
    assert not row.button.isHidden()

    row.button.click()
    row.editor.setText("Never mind")
    QTest.keyClick(row.editor, Qt.Key.Key_Escape)
    app.processEvents()

    assert submitted == [("phase", "Feed Kumquat", True)]
    assert row.editor.isHidden()
    assert not row.button.isHidden()


def test_add_quest_row_commits_pending_text_when_focus_leaves(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    submitted = []
    widget.task_add_requested.connect(
        lambda phase_id, title, refocus: submitted.append((phase_id, title, refocus))
    )
    row = widget.findChild(AddQuestRow, "add-quest-phase")

    row.button.click()
    row.editor.setText("Water plants")
    QApplication.sendEvent(
        row.editor, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason)
    )
    app.processEvents()

    assert submitted == [("phase", "Water plants", False)]
    assert row.editor.isHidden()


def test_main_window_inline_add_persists_and_reopens_editor(app):
    task_service, repository = service()
    window = MainWindow(task_service, restore_position=False)
    row = window.task_list.findChild(AddQuestRow, "add-quest-phase")

    row.start_editing()
    row.editor.setText("New quest")
    QTest.keyClick(row.editor, Qt.Key.Key_Return)
    app.processEvents()

    assert repository.save_count == 1
    assert [task.title for task in task_service.document.phases[0].tasks] == [
        "Toggle me",
        "New quest",
    ]
    # Flush deferred deletions so a zombie pre-rebuild row cannot satisfy
    # the assertion below; the open editor must belong to a live row.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    open_editors = [
        candidate
        for candidate in window.task_list.findChildren(AddQuestRow, "add-quest-phase")
        if not candidate.editor.isHidden()
    ]
    assert len(open_editors) == 1  # Enter reopens the editor for the next quest
    window.close()


def test_main_window_inline_add_failure_shows_error_and_does_not_reopen_editor(
    app, monkeypatch
):
    task_service, repository = service()
    window = MainWindow(task_service, restore_position=False)
    errors = []
    monkeypatch.setattr(
        window, "_show_error", lambda title, error: errors.append((title, error))
    )

    def failing_save(document):
        raise OSError("disk full")

    monkeypatch.setattr(repository, "save", failing_save)
    row = window.task_list.findChild(AddQuestRow, "add-quest-phase")

    row.start_editing()
    row.editor.setText("Doomed quest")
    QTest.keyClick(row.editor, Qt.Key.Key_Return)
    app.processEvents()

    assert len(errors) == 1
    assert [task.title for task in task_service.document.phases[0].tasks] == ["Toggle me"]
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    open_editors = [
        candidate
        for candidate in window.task_list.findChildren(AddQuestRow)
        if not candidate.editor.isHidden()
    ]
    assert open_editors == []  # a failed add must not reopen the editor
    window.close()


def test_close_commits_pending_inline_quest(app):
    task_service, repository = service()
    window = MainWindow(task_service, restore_position=False)
    row = window.task_list.findChild(AddQuestRow, "add-quest-phase")

    row.start_editing()
    row.editor.setText("Last minute quest")
    window.close()

    assert repository.save_count == 1
    assert [task.title for task in task_service.document.phases[0].tasks] == [
        "Toggle me",
        "Last minute quest",
    ]


def test_dragging_mini_cat_moves_window_without_restoring(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    window.show()
    app.processEvents()
    window._minimize()
    start = window.pos()
    page = window.mini_page

    QTest.mousePress(page, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    delta = QApplication.startDragDistance() + 30
    for step in (delta // 2, delta):
        local = QPointF(10 + step, 10)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            local,
            QPointF(page.mapToGlobal(local.toPoint())),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(page, move)

    assert window.cat.state == CatState.ANGRY  # dragging makes her grumpy
    assert window.pos() != start
    QTest.mouseRelease(page, Qt.MouseButton.LeftButton, pos=QPoint(10 + delta, 10))

    assert window.stack.currentWidget() is window.mini_page  # a drag never restores
    assert window.cat.state == CatState.AWAKE
    window.close()


def test_restore_lands_on_the_screen_the_cat_is_on(app, monkeypatch):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    window.show()
    app.processEvents()
    screens = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 1920, 1080)]
    monkeypatch.setattr(window, "_screen_geometries", lambda: screens)
    window._minimize()
    window.move(QPoint(1930, 0))  # cat parked at the top-left of the RIGHT monitor

    window._restore_from_cat()

    assert screens[1].contains(QRect(window.pos(), window.size()))
    window.close()


def test_clicking_cat_minimizes_the_card(app):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    window.show()
    app.processEvents()

    QTest.mouseClick(window.cat, Qt.MouseButton.LeftButton)

    assert window.stack.currentWidget() is window.mini_page
    window.close()


def test_unrelated_mutation_preserves_in_progress_rename(app):
    # A rebuild triggered by something else entirely (here: marking every
    # quest complete) must not discard whatever the user is mid-typing into
    # an unrelated quest's rename editor.
    repository = MemoryRepository()
    repository.document = BuddyDocument(
        schema_version=1,
        title="TEST",
        phases=[
            Phase(
                id="phase",
                title="PHASE",
                tasks=[Task(id="task-a", title="Task A"), Task(id="task-b", title="Task B")],
            )
        ],
        sync=SyncMetadata(),
    )
    task_service = TaskService(repository)
    task_service.load_or_initialize()
    window = MainWindow(task_service, restore_position=False)
    row_a = next(r for r in window.task_list.findChildren(TaskRow) if r.task_id == "task-a")

    QTest.mouseDClick(row_a, Qt.MouseButton.LeftButton)
    editor_a = row_a.findChild(QLineEdit, "taskTitleEditor")
    QTest.keyClicks(editor_a, "Task A in progress")

    window._mark_all_complete()  # unrelated mutation elsewhere rebuilds the list

    new_row_a = next(r for r in window.task_list.findChildren(TaskRow) if r.task_id == "task-a")
    new_editor_a = new_row_a.findChild(QLineEdit, "taskTitleEditor")
    assert not new_editor_a.isHidden()
    assert new_editor_a.text() == "Task A in progress"
    window.close()


def test_close_commits_pending_inline_rename(app):
    task_service, repository = service()
    window = MainWindow(task_service, restore_position=False)
    row = window.task_list.findChild(TaskRow, "taskRow")

    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
    editor = row.findChild(QLineEdit, "taskTitleEditor")
    QTest.keyClicks(editor, "Renamed before close")
    window.close()

    assert [task.title for task in task_service.document.phases[0].tasks] == [
        "Renamed before close"
    ]


def test_change_phase_color_applies_chosen_color(app, monkeypatch):
    task_service, _ = service()
    window = MainWindow(task_service, restore_position=False)
    monkeypatch.setattr(
        main_window_module, "choose_color", lambda parent, title, current: "#123456"
    )

    window._change_phase_color("phase")

    assert task_service.document.phases[0].color == "#123456"
    window.close()


def test_color_swatch_picker_selection(app):
    picker = ColorSwatchPicker(current="#D4A54E")
    assert picker.selected_color == "#D4A54E"

    picker.findChild(QPushButton, "swatch-#5B78C7").click()

    assert picker.selected_color == "#5B78C7"


def test_action_dialog_never_defaults_to_the_destructive_action(app):
    # A stray Enter/Return must never fire a delete; only a non-destructive
    # confirm (a color pick, say) is allowed to be the default button.
    danger_dialog = action_dialog.ActionDialog(
        None, "Delete quest?", confirm_text="Delete", danger=True
    )
    assert danger_dialog.findChild(QPushButton, "primaryButton").isDefault() is False

    safe_dialog = action_dialog.ActionDialog(None, "Apply", confirm_text="Apply", danger=False)
    assert safe_dialog.findChild(QPushButton, "primaryButton").isDefault() is True


def test_double_click_while_already_editing_does_not_discard_typed_text(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    row = widget.findChild(TaskRow, "taskRow")

    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
    editor = row.findChild(QLineEdit, "taskTitleEditor")
    editor.selectAll()
    QTest.keyClicks(editor, "typed but not yet committed")

    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)  # a stray second double-click

    assert editor.text() == "typed but not yet committed"


def test_action_dialog_confirm_button_is_labeled_and_accepts(app):
    # Constructed but never exec()'d/shown: a real exec() would block this
    # headless test process, so we drive the dialog's buttons directly.
    dialog = action_dialog.ActionDialog(
        None, "Delete quest?", message="This cannot be undone.", confirm_text="Delete", danger=True
    )

    confirm_button = dialog.findChild(QPushButton, "primaryButton")
    assert confirm_button.text() == "Delete"

    confirm_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_choose_color_reflects_dialog_result(app, monkeypatch):
    monkeypatch.setattr(
        action_dialog.ActionDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    assert choose_color(None, "Choose category color", "#5B78C7") == "#5B78C7"

    monkeypatch.setattr(
        action_dialog.ActionDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    assert choose_color(None, "Choose category color", "#5B78C7") is None


def test_confirm_delete_and_reset_use_action_dialog(app, monkeypatch):
    monkeypatch.setattr(
        action_dialog.ActionDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    assert dialogs.confirm_delete(None, "Delete?", "Sure?") is True
    assert dialogs.confirm_reset(None) is True

    monkeypatch.setattr(
        action_dialog.ActionDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    assert dialogs.confirm_delete(None, "Delete?", "Sure?") is False
    assert dialogs.confirm_reset(None) is False


def test_position_is_clamped_to_nearest_visible_work_area():
    screens = [QRect(0, 0, 1920, 1040), QRect(1920, 0, 1920, 1040)]

    assert clamp_position(QPoint(-900, -500), 334, 650, screens) == QPoint(0, 0)
    assert clamp_position(QPoint(5000, 900), 334, 650, screens) == QPoint(3506, 390)
    assert clamp_position(QPoint(2000, 100), 334, 650, screens) == QPoint(2000, 100)
