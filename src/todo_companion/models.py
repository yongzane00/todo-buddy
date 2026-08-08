from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
from typing import Any, Literal


class DocumentValidationError(ValueError):
    """Raised when persisted task data does not match the supported schema."""


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError(f"{location} must be an object")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentValidationError(f"{location} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, location: str) -> str | None:
    if value is None:
        return None
    return _text(value, location)


def _color(value: Any, location: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None:
        raise DocumentValidationError(f"{location} must be a #RRGGBB color or null")
    return value.upper()


def _datetime(value: Any, location: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DocumentValidationError(f"{location} must be an ISO-8601 timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DocumentValidationError(f"{location} must be a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise DocumentValidationError(f"{location} must include a timezone")
    return parsed.astimezone(UTC)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise DocumentValidationError("completed_at must include a timezone")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Task:
    id: str
    title: str
    completed: bool = False
    completed_at: datetime | None = None
    source: Literal["local", "microsoft_todo"] = "local"
    remote_id: str | None = None

    def set_completed(self, completed: bool, now: datetime | None = None) -> None:
        if not isinstance(completed, bool):
            raise DocumentValidationError("completed must be true or false")
        if completed:
            moment = now or datetime.now(UTC)
            if moment.tzinfo is None:
                raise DocumentValidationError("completion timestamp must include a timezone")
            if not self.completed or self.completed_at is None:
                self.completed_at = moment.astimezone(UTC)
        else:
            self.completed_at = None
        self.completed = completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "completed": self.completed,
            "completed_at": _isoformat(self.completed_at),
            "source": self.source,
            "remote_id": self.remote_id,
        }

    @classmethod
    def from_dict(cls, value: Any, location: str = "task") -> Task:
        data = _mapping(value, location)
        completed = data.get("completed", False)
        if not isinstance(completed, bool):
            raise DocumentValidationError(f"{location}.completed must be true or false")
        completed_at = _datetime(data.get("completed_at"), f"{location}.completed_at")
        if not completed and completed_at is not None:
            raise DocumentValidationError(
                f"{location}.completed_at must be null when completed is false"
            )
        source = data.get("source", "local")
        if source not in ("local", "microsoft_todo"):
            raise DocumentValidationError(f"{location}.source is not supported")
        return cls(
            id=_text(data.get("id"), f"{location}.id"),
            title=_text(data.get("title"), f"{location}.title"),
            completed=completed,
            completed_at=completed_at,
            source=source,
            remote_id=_optional_text(data.get("remote_id"), f"{location}.remote_id"),
        )


@dataclass
class Phase:
    id: str
    title: str
    tasks: list[Task] = field(default_factory=list)
    color: str | None = None

    def set_color(self, color: str | None) -> None:
        self.color = _color(color, "phase.color")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "tasks": [task.to_dict() for task in self.tasks],
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, value: Any, location: str = "phase") -> Phase:
        data = _mapping(value, location)
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise DocumentValidationError(f"{location}.tasks must be an array")
        return cls(
            id=_text(data.get("id"), f"{location}.id"),
            title=_text(data.get("title"), f"{location}.title"),
            tasks=[Task.from_dict(task, f"{location}.tasks[{index}]") for index, task in enumerate(tasks)],
            color=_color(data.get("color"), f"{location}.color"),
        )


@dataclass
class SyncMetadata:
    provider: str | None = None
    enabled: bool = False
    task_list_id: str | None = None
    last_sync_at: datetime | None = None
    delta_link: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "task_list_id": self.task_list_id,
            "last_sync_at": _isoformat(self.last_sync_at),
            "delta_link": self.delta_link,
        }

    @classmethod
    def from_dict(cls, value: Any) -> SyncMetadata:
        data = _mapping(value, "sync")
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise DocumentValidationError("sync.enabled must be true or false")
        provider = data.get("provider")
        if provider not in (None, "microsoft_todo"):
            raise DocumentValidationError("sync.provider is not supported")
        return cls(
            provider=provider,
            enabled=enabled,
            task_list_id=_optional_text(data.get("task_list_id"), "sync.task_list_id"),
            last_sync_at=_datetime(data.get("last_sync_at"), "sync.last_sync_at"),
            delta_link=_optional_text(data.get("delta_link"), "sync.delta_link"),
        )


@dataclass
class CompanionDocument:
    schema_version: int
    title: str
    phases: list[Phase]
    sync: SyncMetadata = field(default_factory=SyncMetadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "phases": [phase.to_dict() for phase in self.phases],
            "sync": self.sync.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> CompanionDocument:
        data = _mapping(value, "document")
        if "schema_version" not in data:
            raise DocumentValidationError("schema_version is required")
        if data["schema_version"] != 1:
            raise DocumentValidationError(
                f"Unsupported schema version: {data['schema_version']!r}; expected 1"
            )
        phases = data.get("phases")
        if not isinstance(phases, list):
            raise DocumentValidationError("phases must be an array")
        document = cls(
            schema_version=1,
            title=_text(data.get("title"), "title"),
            phases=[Phase.from_dict(phase, f"phases[{index}]") for index, phase in enumerate(phases)],
            sync=SyncMetadata.from_dict(data.get("sync", {})),
        )
        document._validate_unique_ids()
        return document

    def _validate_unique_ids(self) -> None:
        phase_ids: set[str] = set()
        task_ids: set[str] = set()
        for phase in self.phases:
            if phase.id in phase_ids:
                raise DocumentValidationError(f"Duplicate phase id: {phase.id}")
            phase_ids.add(phase.id)
            for task in phase.tasks:
                if task.id in task_ids:
                    raise DocumentValidationError(f"Duplicate task id: {task.id}")
                task_ids.add(task.id)
