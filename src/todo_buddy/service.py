from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from todo_buddy.models import BuddyDocument, Phase, Task
from todo_buddy.sample_data import create_sample_document


class Repository(Protocol):
    def load(self) -> BuddyDocument: ...
    def save(self, document: BuddyDocument) -> None: ...
    def backup(self): ...


class ServiceError(ValueError):
    pass


class TitleError(ServiceError):
    pass


class ItemNotFoundError(ServiceError):
    pass


class TaskService:
    def __init__(
        self,
        repository: Repository,
        now: Callable[[], datetime] | None = None,
        sample_factory: Callable[[], BuddyDocument] = create_sample_document,
    ):
        self.repository = repository
        self._now = now or (lambda: datetime.now(UTC))
        self._sample_factory = sample_factory
        self._document: BuddyDocument | None = None

    @property
    def document(self) -> BuddyDocument:
        if self._document is None:
            raise RuntimeError("TaskService must be loaded before use")
        return self._document

    def load_or_initialize(self) -> BuddyDocument:
        self._document = self.repository.load()
        return self._document

    def progress(self) -> tuple[int, int]:
        tasks = [task for phase in self.document.phases for task in phase.tasks]
        return sum(task.completed for task in tasks), len(tasks)

    def next_incomplete_task(self) -> Task | None:
        return next(
            (task for phase in self.document.phases for task in phase.tasks if not task.completed),
            None,
        )

    def set_task_completion(self, task_id: str, completed: bool) -> BuddyDocument:
        candidate = self._copy_document()
        task = next(
            (task for phase in candidate.phases for task in phase.tasks if task.id == task_id),
            None,
        )
        if task is None:
            raise ItemNotFoundError(f"Task not found: {task_id}")
        task.set_completed(completed, now=self._now())
        return self._save(candidate)

    def add_task(self, phase_id: str, title: str) -> BuddyDocument:
        clean_title = self._clean_title(title)
        candidate = self._copy_document()
        phase = next((phase for phase in candidate.phases if phase.id == phase_id), None)
        if phase is None:
            raise ItemNotFoundError(f"Phase not found: {phase_id}")
        phase.tasks.append(Task(id=str(uuid4()), title=clean_title))
        return self._save(candidate)

    def add_phase(self, title: str) -> BuddyDocument:
        clean_title = self._clean_title(title)
        candidate = self._copy_document()
        candidate.phases.append(Phase(id=str(uuid4()), title=clean_title, tasks=[]))
        return self._save(candidate)

    def rename_task(self, task_id: str, title: str) -> BuddyDocument:
        clean_title = self._clean_title(title)
        candidate = self._copy_document()
        task = next(
            (task for phase in candidate.phases for task in phase.tasks if task.id == task_id),
            None,
        )
        if task is None:
            raise ItemNotFoundError(f"Task not found: {task_id}")
        task.title = clean_title
        return self._save(candidate)

    def delete_task(self, task_id: str) -> BuddyDocument:
        candidate = self._copy_document()
        for phase in candidate.phases:
            for index, task in enumerate(phase.tasks):
                if task.id == task_id:
                    del phase.tasks[index]
                    return self._save(candidate)
        raise ItemNotFoundError(f"Task not found: {task_id}")

    def rename_phase(self, phase_id: str, title: str) -> BuddyDocument:
        clean_title = self._clean_title(title)
        candidate = self._copy_document()
        phase = next((phase for phase in candidate.phases if phase.id == phase_id), None)
        if phase is None:
            raise ItemNotFoundError(f"Phase not found: {phase_id}")
        phase.title = clean_title
        return self._save(candidate)

    def delete_phase(self, phase_id: str) -> BuddyDocument:
        candidate = self._copy_document()
        for index, phase in enumerate(candidate.phases):
            if phase.id == phase_id:
                del candidate.phases[index]
                return self._save(candidate)
        raise ItemNotFoundError(f"Phase not found: {phase_id}")

    def set_all_tasks_completion(self, completed: bool) -> BuddyDocument:
        candidate = self._copy_document()
        now = self._now()
        for phase in candidate.phases:
            for task in phase.tasks:
                task.set_completed(completed, now=now)
        return self._save(candidate)

    def delete_completed_tasks(self) -> BuddyDocument:
        candidate = self._copy_document()
        for phase in candidate.phases:
            phase.tasks = [task for task in phase.tasks if not task.completed]
        return self._save(candidate)

    def move_task(
        self, task_id: str, destination_phase_id: str, destination_index: int
    ) -> BuddyDocument:
        candidate = self._copy_document()
        destination = next(
            (phase for phase in candidate.phases if phase.id == destination_phase_id), None
        )
        if destination is None:
            raise ItemNotFoundError(f"Phase not found: {destination_phase_id}")

        source = None
        source_index = -1
        moving_task = None
        for phase in candidate.phases:
            for index, task in enumerate(phase.tasks):
                if task.id == task_id:
                    source = phase
                    source_index = index
                    moving_task = task
                    break
            if moving_task is not None:
                break
        if source is None or moving_task is None:
            raise ItemNotFoundError(f"Task not found: {task_id}")

        maximum = len(destination.tasks) - (1 if source is destination else 0)
        if (
            not isinstance(destination_index, int)
            or isinstance(destination_index, bool)
            or not 0 <= destination_index <= maximum
        ):
            raise ValueError(
                f"Destination index must be between 0 and {maximum}: {destination_index!r}"
            )
        if source is destination and source_index == destination_index:
            return self.document

        source.tasks.pop(source_index)
        destination.tasks.insert(destination_index, moving_task)
        return self._save(candidate)

    def set_phase_color(self, phase_id: str, color: str | None) -> BuddyDocument:
        candidate = self._copy_document()
        phase = next((phase for phase in candidate.phases if phase.id == phase_id), None)
        if phase is None:
            raise ItemNotFoundError(f"Phase not found: {phase_id}")
        phase.set_color(color)
        return self._save(candidate)

    def rename_document(self, title: str) -> BuddyDocument:
        candidate = self._copy_document()
        candidate.title = self._clean_title(title)
        return self._save(candidate)

    def reset_sample_data(self) -> BuddyDocument:
        candidate = self._sample_factory()
        self.repository.backup()
        return self._save(candidate)

    def _copy_document(self) -> BuddyDocument:
        return BuddyDocument.from_dict(self.document.to_dict())

    def _save(self, candidate: BuddyDocument) -> BuddyDocument:
        self.repository.save(candidate)
        self._document = candidate
        return candidate

    @staticmethod
    def _clean_title(title: str) -> str:
        if not isinstance(title, str) or not title.strip():
            raise TitleError("Title cannot be blank")
        return title.strip()
