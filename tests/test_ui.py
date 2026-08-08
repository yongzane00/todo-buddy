import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QDropEvent, QFocusEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from todo_buddy.models import BuddyDocument, Phase, SyncMetadata, Task
from todo_buddy.service import TaskService
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


def test_task_and_phase_action_menus_emit_item_ids(app):
    task_service, _ = service()
    widget = TaskListWidget()
    widget.set_document(task_service.document)
    requested = []
    widget.task_edit_requested.connect(lambda item_id: requested.append(("edit-task", item_id)))
    widget.task_delete_requested.connect(lambda item_id: requested.append(("delete-task", item_id)))
    widget.phase_edit_requested.connect(lambda item_id: requested.append(("edit-phase", item_id)))
    widget.phase_delete_requested.connect(lambda item_id: requested.append(("delete-phase", item_id)))
    widget.phase_color_requested.connect(lambda item_id: requested.append(("color-phase", item_id)))

    task_menu = widget.findChild(QToolButton, "task-actions-task").menu()
    phase_menu = widget.findChild(QToolButton, "phase-actions-phase").menu()
    task_menu.actions()[0].trigger()
    task_menu.actions()[1].trigger()
    phase_menu.actions()[0].trigger()
    phase_menu.actions()[1].trigger()
    phase_menu.actions()[2].trigger()

    assert requested == [
        ("edit-task", "task"),
        ("delete-task", "task"),
        ("edit-phase", "phase"),
        ("color-phase", "phase"),
        ("delete-phase", "phase"),
    ]


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
    open_editors = [
        candidate
        for candidate in window.task_list.findChildren(AddQuestRow, "add-quest-phase")
        if not candidate.editor.isHidden()
    ]
    assert len(open_editors) == 1  # Enter reopens the editor for the next quest
    window.close()


def test_position_is_clamped_to_nearest_visible_work_area():
    screens = [QRect(0, 0, 1920, 1040), QRect(1920, 0, 1920, 1040)]

    assert clamp_position(QPoint(-900, -500), 334, 650, screens) == QPoint(0, 0)
    assert clamp_position(QPoint(5000, 900), 334, 650, screens) == QPoint(3506, 390)
    assert clamp_position(QPoint(2000, 100), 334, 650, screens) == QPoint(2000, 100)
