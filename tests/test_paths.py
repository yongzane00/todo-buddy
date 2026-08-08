from pathlib import Path

from todo_companion.paths import resolve_data_path


def test_explicit_data_path_wins(monkeypatch, tmp_path):
    requested = tmp_path / "custom" / "my-tasks.json"
    monkeypatch.setenv("TODO_COMPANION_DATA_PATH", str(requested))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert resolve_data_path() == requested


def test_default_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_COMPANION_DATA_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert resolve_data_path() == Path(tmp_path) / "TodoCompanion" / "tasks.json"
