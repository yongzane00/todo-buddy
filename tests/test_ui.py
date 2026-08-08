import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QToolButton

from todo_companion.models import CompanionDocument, Phase, SyncMetadata, Task
from todo_companion.service import TaskService
from todo_companion.ui.main_window import MainWindow, clamp_position
from todo_companion.ui.cat_widget import CatState, CatWidget
from todo_companion.ui.task_list_widget import (
    TASK_MIME_TYPE,
    QuestCheckBox,
    TaskDropArea,
    TaskListWidget,
)


class MemoryRepository:
    def __init__(self):
        self.document = CompanionDocument(
            schema_version=1,
            title="UI TEST QUEST",
            phases=[Phase(id="phase", title="PHASE 1: TEST", tasks=[Task(id="task", title="Toggle me")])],
            sync=SyncMetadata(),
        )
        self.save_count = 0

    def load(self):
        return CompanionDocument.from_dict(self.document.to_dict())

    def save(self, document):
        self.save_count += 1
        self.document = CompanionDocument.from_dict(document.to_dict())

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


def test_main_window_uses_companion_window_flags_and_transparency(app):
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
    assert button.accessibleName() == "Minimize Todo Companion"
    window.close()


def test_position_is_clamped_to_nearest_visible_work_area():
    screens = [QRect(0, 0, 1920, 1040), QRect(1920, 0, 1920, 1040)]

    assert clamp_position(QPoint(-900, -500), 334, 650, screens) == QPoint(0, 0)
    assert clamp_position(QPoint(5000, 900), 334, 650, screens) == QPoint(3506, 390)
    assert clamp_position(QPoint(2000, 100), 334, 650, screens) == QPoint(2000, 100)
