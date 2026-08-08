from datetime import UTC, datetime

import pytest

from todo_companion.models import CompanionDocument, Phase, SyncMetadata, Task
from todo_companion.service import ItemNotFoundError, TaskService, TitleError


class MemoryRepository:
    def __init__(self, document):
        self.document = document
        self.save_count = 0
        self.backup_count = 0

    def load(self):
        return CompanionDocument.from_dict(self.document.to_dict())

    def save(self, document):
        self.save_count += 1
        self.document = CompanionDocument.from_dict(document.to_dict())

    def backup(self):
        self.backup_count += 1
        return None


def document() -> CompanionDocument:
    return CompanionDocument(
        schema_version=1,
        title="Make something useful",
        phases=[
            Phase(id="one", title="PHASE 1", tasks=[
                Task(id="a", title="First", completed=True,
                     completed_at=datetime(2026, 8, 5, 7, tzinfo=UTC)),
                Task(id="b", title="Second"),
            ]),
            Phase(id="two", title="PHASE 2", tasks=[Task(id="c", title="Third")]),
        ],
        sync=SyncMetadata(),
    )


def loaded_service():
    repository = MemoryRepository(document())
    service = TaskService(repository, now=lambda: datetime(2026, 8, 5, 9, tzinfo=UTC))
    service.load_or_initialize()
    return service, repository


def test_progress_counts_all_phases():
    service, _ = loaded_service()
    assert service.progress() == (1, 3)


def test_completion_updates_timestamp_and_persists_once():
    service, repository = loaded_service()

    result = service.set_task_completion("b", True)

    assert result.phases[0].tasks[1].completed_at == datetime(2026, 8, 5, 9, tzinfo=UTC)
    assert repository.save_count == 1


def test_next_incomplete_respects_display_order():
    service, _ = loaded_service()
    assert service.next_incomplete_task().id == "b"
    service.set_task_completion("b", True)
    assert service.next_incomplete_task().id == "c"
    service.set_task_completion("c", True)
    assert service.next_incomplete_task() is None


def test_add_task_and_phase_generate_ids_and_trim_titles():
    service, repository = loaded_service()

    added_task = service.add_task("one", "  New task  ").phases[0].tasks[-1]
    added_phase = service.add_phase("  PHASE 3: POLISH  ").phases[-1]

    assert added_task.id and added_task.title == "New task"
    assert added_phase.id and added_phase.title == "PHASE 3: POLISH"
    assert repository.save_count == 2


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_titles_are_rejected(value):
    service, repository = loaded_service()

    with pytest.raises(TitleError):
        service.add_task("one", value)
    with pytest.raises(TitleError):
        service.add_phase(value)
    with pytest.raises(TitleError):
        service.rename_document(value)
    with pytest.raises(TitleError):
        service.rename_task("a", value)
    with pytest.raises(TitleError):
        service.rename_phase("one", value)

    assert repository.save_count == 0


def test_rename_trims_title():
    service, repository = loaded_service()
    assert service.rename_document("  Focus card  ").title == "Focus card"
    assert repository.save_count == 1


def test_unknown_ids_do_not_save():
    service, repository = loaded_service()
    with pytest.raises(ItemNotFoundError):
        service.set_task_completion("missing", True)
    with pytest.raises(ItemNotFoundError):
        service.add_task("missing", "No destination")
    with pytest.raises(ItemNotFoundError):
        service.rename_task("missing", "No task")
    with pytest.raises(ItemNotFoundError):
        service.delete_task("missing")
    with pytest.raises(ItemNotFoundError):
        service.rename_phase("missing", "No phase")
    with pytest.raises(ItemNotFoundError):
        service.delete_phase("missing")
    assert repository.save_count == 0


def test_reset_backs_up_then_saves_sample():
    service, repository = loaded_service()

    result = service.reset_sample_data()

    assert result.title == "BUILD A THOUGHTFUL DEMO"
    assert repository.backup_count == 1
    assert repository.save_count == 1


def test_rename_task_preserves_completion_and_saves_once():
    service, repository = loaded_service()

    result = service.rename_task("a", "  Edited first quest  ")
    renamed = result.phases[0].tasks[0]

    assert renamed.title == "Edited first quest"
    assert renamed.completed is True
    assert renamed.completed_at == datetime(2026, 8, 5, 7, tzinfo=UTC)
    assert repository.save_count == 1


def test_delete_task_removes_only_requested_task():
    service, repository = loaded_service()

    result = service.delete_task("b")

    assert [task.id for phase in result.phases for task in phase.tasks] == ["a", "c"]
    assert repository.save_count == 1


def test_rename_and_delete_phase_persist_once_each():
    service, repository = loaded_service()

    renamed = service.rename_phase("two", "  PHASE 2: SHIP  ")
    assert renamed.phases[1].title == "PHASE 2: SHIP"

    deleted = service.delete_phase("one")
    assert [phase.id for phase in deleted.phases] == ["two"]
    assert repository.save_count == 2


def test_set_all_completion_updates_every_task_in_one_save():
    service, repository = loaded_service()

    completed = service.set_all_tasks_completion(True)

    assert all(task.completed for phase in completed.phases for task in phase.tasks)
    assert all(task.completed_at is not None for phase in completed.phases for task in phase.tasks)
    assert repository.save_count == 1

    incomplete = service.set_all_tasks_completion(False)
    assert not any(task.completed for phase in incomplete.phases for task in phase.tasks)
    assert not any(task.completed_at for phase in incomplete.phases for task in phase.tasks)
    assert repository.save_count == 2


def test_delete_completed_tasks_keeps_incomplete_tasks_and_empty_phases():
    service, repository = loaded_service()

    result = service.delete_completed_tasks()

    assert [task.id for phase in result.phases for task in phase.tasks] == ["b", "c"]
    assert [phase.id for phase in result.phases] == ["one", "two"]
    assert repository.save_count == 1


def test_move_task_reorders_within_phase_and_persists_once():
    service, repository = loaded_service()

    result = service.move_task("a", "one", 1)

    assert [task.id for task in result.phases[0].tasks] == ["b", "a"]
    assert result.phases[0].tasks[1].completed_at == datetime(2026, 8, 5, 7, tzinfo=UTC)
    assert repository.save_count == 1


def test_move_task_crosses_phase_and_supports_empty_destination():
    service, repository = loaded_service()
    service.add_phase("EMPTY")
    repository.save_count = 0
    empty_id = service.document.phases[-1].id

    result = service.move_task("b", empty_id, 0)

    assert [task.id for task in result.phases[0].tasks] == ["a"]
    assert [task.id for task in result.phases[-1].tasks] == ["b"]
    assert repository.save_count == 1


def test_move_task_rejects_unknown_destination_and_invalid_index_without_save():
    service, repository = loaded_service()

    with pytest.raises(ItemNotFoundError):
        service.move_task("a", "missing", 0)
    with pytest.raises(ValueError, match="index"):
        service.move_task("a", "one", 3)

    assert repository.save_count == 0


def test_same_position_move_is_a_no_op():
    service, repository = loaded_service()

    result = service.move_task("b", "one", 1)

    assert result is service.document
    assert repository.save_count == 0


def test_set_phase_color_normalizes_and_persists():
    service, repository = loaded_service()

    result = service.set_phase_color("one", "#2f6fed")

    assert result.phases[0].color == "#2F6FED"
    assert repository.save_count == 1
