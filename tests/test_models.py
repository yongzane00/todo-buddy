from datetime import UTC, datetime

import pytest

from todo_companion.models import (
    CompanionDocument,
    DocumentValidationError,
    Phase,
    SyncMetadata,
    Task,
)


def make_document() -> CompanionDocument:
    return CompanionDocument(
        schema_version=1,
        title="Ship a tiny app",
        phases=[
            Phase(
                id="phase-1",
                title="PHASE 1: PLAN",
                tasks=[Task(id="task-1", title="Write the plan", completed=True,
                            completed_at=datetime(2026, 8, 5, 8, tzinfo=UTC))],
            )
        ],
        sync=SyncMetadata(),
    )


def test_document_round_trip_preserves_content():
    restored = CompanionDocument.from_dict(make_document().to_dict())

    assert restored.title == "Ship a tiny app"
    assert restored.phases[0].title == "PHASE 1: PLAN"
    assert restored.phases[0].tasks[0].completed is True
    assert restored.phases[0].tasks[0].completed_at == datetime(2026, 8, 5, 8, tzinfo=UTC)


def test_task_completion_normalizes_utc_timestamp_and_clears_it():
    task = Task(id="task-1", title="Test persistence")
    local_time = datetime(2026, 8, 5, 16, tzinfo=UTC)

    task.set_completed(True, now=local_time)
    assert task.completed is True
    assert task.completed_at == local_time
    assert task.to_dict()["completed_at"] == "2026-08-05T16:00:00Z"

    task.set_completed(False)
    assert task.completed is False
    assert task.completed_at is None


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "schema_version"),
        ({"schema_version": 99, "title": "x", "phases": [], "sync": {}}, "schema version"),
        ({"schema_version": 1, "title": " ", "phases": [], "sync": {}}, "title"),
        ({"schema_version": 1, "title": "x", "phases": "bad", "sync": {}}, "phases"),
    ],
)
def test_invalid_document_has_clear_error(payload, message):
    with pytest.raises(DocumentValidationError, match=message):
        CompanionDocument.from_dict(payload)


def test_incomplete_task_cannot_retain_completion_timestamp():
    payload = make_document().to_dict()
    payload["phases"][0]["tasks"][0]["completed"] = False

    with pytest.raises(DocumentValidationError, match="completed_at"):
        CompanionDocument.from_dict(payload)


def test_phase_color_round_trips_and_old_data_uses_default():
    payload = make_document().to_dict()
    payload["phases"][0]["color"] = "#2F6FED"

    restored = CompanionDocument.from_dict(payload)
    assert restored.phases[0].color == "#2F6FED"
    assert restored.to_dict()["phases"][0]["color"] == "#2F6FED"

    del payload["phases"][0]["color"]
    assert CompanionDocument.from_dict(payload).phases[0].color is None


@pytest.mark.parametrize("color", ["red", "#123", "#GG0000", 42])
def test_invalid_phase_color_is_rejected(color):
    payload = make_document().to_dict()
    payload["phases"][0]["color"] = color

    with pytest.raises(DocumentValidationError, match="color"):
        CompanionDocument.from_dict(payload)
