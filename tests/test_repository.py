import json

import pytest

from todo_buddy.models import BuddyDocument, Phase, SyncMetadata, Task
from todo_buddy.repository import JsonRepository, RepositoryError


def sample() -> BuddyDocument:
    return BuddyDocument(
        schema_version=1,
        title="Sample quest",
        phases=[Phase(id="phase", title="PHASE 1", tasks=[Task(id="task", title="Start")])],
        sync=SyncMetadata(),
    )


def test_missing_file_returns_default_without_writing(tmp_path):
    path = tmp_path / "nested" / "tasks.json"
    repository = JsonRepository(path, sample)

    loaded = repository.load()

    assert loaded.title == "Sample quest"
    assert not path.exists()


def test_save_load_round_trip(tmp_path):
    path = tmp_path / "tasks.json"
    repository = JsonRepository(path, sample)
    document = sample()
    document.title = "Persisted quest"

    repository.save(document)

    assert repository.load() == document


def test_save_is_parseable_and_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "tasks.json"
    JsonRepository(path, sample).save(sample())

    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert list(tmp_path.glob("*.tmp")) == []


def test_malformed_json_is_preserved(tmp_path):
    path = tmp_path / "tasks.json"
    original = b'{"schema_version": 1, broken'
    path.write_bytes(original)

    with pytest.raises(RepositoryError, match="could not be read"):
        JsonRepository(path, sample).load()

    assert path.read_bytes() == original


def test_backup_copies_existing_data(tmp_path):
    path = tmp_path / "tasks.json"
    repository = JsonRepository(path, sample)
    repository.save(sample())

    backup = repository.backup()

    assert backup is not None
    assert backup.exists()
    assert backup.read_bytes() == path.read_bytes()
