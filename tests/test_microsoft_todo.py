import pytest

from todo_companion.integrations.microsoft_todo import (
    GraphMappingError,
    completion_update_payload,
    map_graph_task,
)


def test_graph_task_mapping_uses_title_status_and_remote_id():
    remote = map_graph_task({"id": "AQMk-123", "title": "Review draft", "status": "completed"})

    assert remote.id == "AQMk-123"
    assert remote.title == "Review draft"
    assert remote.completed is True


@pytest.mark.parametrize("completed,status", [(True, "completed"), (False, "notStarted")])
def test_completion_update_uses_graph_status_values(completed, status):
    assert completion_update_payload(completed) == {"status": status}


def test_invalid_graph_task_is_contained_as_mapping_error():
    with pytest.raises(GraphMappingError, match="id"):
        map_graph_task({"title": "Missing remote id", "status": "notStarted"})
