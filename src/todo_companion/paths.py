from __future__ import annotations

import os
from pathlib import Path


def resolve_data_path() -> Path:
    override = os.environ.get("TODO_COMPANION_DATA_PATH")
    if override:
        return Path(override).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "TodoCompanion" / "tasks.json"
