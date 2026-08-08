"""Dependency-free contracts for the optional Microsoft Graph phase.

The MVP does not authenticate or make network requests. Keeping Graph mapping
here prevents future OAuth and HTTP concerns from leaking into the UI/domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from todo_companion.models import Task


class GraphMappingError(ValueError):
    pass


@dataclass(frozen=True)
class RemoteTaskList:
    id: str
    title: str


@dataclass(frozen=True)
class RemoteTask:
    id: str
    title: str
    completed: bool


@dataclass(frozen=True)
class RemoteTaskSyncResult:
    tasks: list[RemoteTask]
    delta_link: str | None = None


class TodoGateway(Protocol):
    def list_task_lists(self) -> list[RemoteTaskList]: ...

    def list_tasks(
        self, list_id: str, delta_link: str | None = None
    ) -> RemoteTaskSyncResult: ...

    def create_task(self, list_id: str, task: Task) -> RemoteTask: ...

    def update_task_completion(
        self, list_id: str, remote_id: str, completed: bool
    ) -> RemoteTask: ...


def map_graph_task(payload: dict[str, Any]) -> RemoteTask:
    remote_id = payload.get("id")
    title = payload.get("title")
    if not isinstance(remote_id, str) or not remote_id:
        raise GraphMappingError("Microsoft Graph task id is missing")
    if not isinstance(title, str) or not title.strip():
        raise GraphMappingError("Microsoft Graph task title is missing")
    return RemoteTask(
        id=remote_id,
        title=title.strip(),
        completed=payload.get("status") == "completed",
    )


def completion_update_payload(completed: bool) -> dict[str, str]:
    return {"status": "completed" if completed else "notStarted"}
