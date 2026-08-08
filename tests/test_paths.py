from pathlib import Path

from todo_buddy.paths import migrate_legacy_data, resolve_data_path


def test_explicit_data_path_wins(monkeypatch, tmp_path):
    requested = tmp_path / "custom" / "my-tasks.json"
    monkeypatch.setenv("TODO_BUDDY_DATA_PATH", str(requested))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert resolve_data_path() == requested


def test_default_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_BUDDY_DATA_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert resolve_data_path() == Path(tmp_path) / "TodoBuddy" / "tasks.json"


def _legacy_file(tmp_path, content='{"schema_version": 1}'):
    legacy = tmp_path / "TodoCompanion" / "tasks.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(content, encoding="utf-8")
    return legacy


def test_legacy_todocompanion_data_is_copied_once(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_BUDDY_DATA_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = _legacy_file(tmp_path)
    new_path = resolve_data_path()

    assert migrate_legacy_data(new_path) is True
    assert new_path.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")
    assert legacy.exists()  # original kept as a backup
    assert migrate_legacy_data(new_path) is False  # second run is a no-op


def test_migration_never_overwrites_existing_data(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_BUDDY_DATA_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _legacy_file(tmp_path, '{"schema_version": 1, "old": true}')
    new_path = resolve_data_path()
    new_path.parent.mkdir(parents=True)
    new_path.write_text('{"schema_version": 1, "new": true}', encoding="utf-8")

    assert migrate_legacy_data(new_path) is False
    assert "new" in new_path.read_text(encoding="utf-8")


def test_failed_migration_leaves_no_partial_file_and_no_sentinel(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_BUDDY_DATA_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # a directory at the legacy path makes the copy raise OSError
    (tmp_path / "TodoCompanion" / "tasks.json").mkdir(parents=True)
    new_path = resolve_data_path()

    assert migrate_legacy_data(new_path) is False
    assert not new_path.exists()  # no partial file blocking a retry
    assert not list(new_path.parent.glob("*.migrating-*"))


def test_migration_skipped_with_explicit_override(monkeypatch, tmp_path):
    override = tmp_path / "override.json"
    monkeypatch.setenv("TODO_BUDDY_DATA_PATH", str(override))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _legacy_file(tmp_path)

    assert migrate_legacy_data(override) is False
    assert not override.exists()
