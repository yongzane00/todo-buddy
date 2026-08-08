from __future__ import annotations

import os
import shutil
from pathlib import Path


def _default_base() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data)
    return Path.home() / "AppData" / "Local"


def resolve_data_path() -> Path:
    override = os.environ.get("TODO_BUDDY_DATA_PATH")
    if override:
        return Path(override).expanduser()
    return _default_base() / "TodoBuddy" / "tasks.json"


def migrate_legacy_data(data_path: Path) -> bool:
    """One-time copy of the pre-rebrand TodoCompanion data file.

    Applies only to the default location: skipped when an explicit
    TODO_BUDDY_DATA_PATH override is set, when the new file already exists,
    or when there is nothing to migrate. The legacy file is left in place
    as a backup.

    The copy is staged and published atomically: data_path doubles as the
    "already migrated" sentinel, so a partial write there would block
    re-migration forever. A failed migration never raises — the app then
    starts from defaults and the legacy file stays intact for a later try.
    """
    if os.environ.get("TODO_BUDDY_DATA_PATH"):
        return False
    legacy = _default_base() / "TodoCompanion" / "tasks.json"
    if data_path.exists() or not legacy.exists():
        return False
    staging = data_path.with_name(f"{data_path.name}.migrating-{os.getpid()}")
    try:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, staging)
        os.replace(staging, data_path)
    except OSError:
        try:
            staging.unlink()
        except OSError:
            pass
        return False
    return True
