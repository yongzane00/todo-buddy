from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from todo_buddy.models import BuddyDocument, DocumentValidationError


class RepositoryError(RuntimeError):
    """A safe, user-displayable persistence failure."""


class JsonRepository:
    def __init__(self, path: Path, default_factory: Callable[[], BuddyDocument]):
        self.path = Path(path)
        self._default_factory = default_factory

    def load(self) -> BuddyDocument:
        if not self.path.exists():
            return self._default_factory()
        try:
            raw = self.path.read_text(encoding="utf-8")
            value = json.loads(raw)
            return BuddyDocument.from_dict(value)
        except (OSError, UnicodeError, json.JSONDecodeError, DocumentValidationError) as error:
            raise RepositoryError(
                f"Task data at '{self.path}' could not be read. The original file was preserved. {error}"
            ) from error

    def save(self, document: BuddyDocument) -> None:
        try:
            validated = BuddyDocument.from_dict(document.to_dict())
            encoded = json.dumps(validated.to_dict(), indent=2, ensure_ascii=False) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.stem}-", suffix=".tmp", dir=self.path.parent
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, self.path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        except (OSError, DocumentValidationError) as error:
            raise RepositoryError(f"Task data could not be saved to '{self.path}'. {error}") from error

    def backup(self) -> Path | None:
        if not self.path.exists():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        candidate = self.path.with_name(f"{self.path.stem}.backup-{stamp}{self.path.suffix}")
        counter = 2
        while candidate.exists():
            candidate = self.path.with_name(
                f"{self.path.stem}.backup-{stamp}-{counter}{self.path.suffix}"
            )
            counter += 1
        try:
            shutil.copy2(self.path, candidate)
        except OSError as error:
            raise RepositoryError(f"Could not back up task data. {error}") from error
        return candidate
