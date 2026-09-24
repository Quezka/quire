from __future__ import annotations

from ...domain import DueBucket, NotFound, Task, TaskKind
from ..bus import ChangeBus, Topic
from ..dto import TaskGroup, TaskItem
from ..inputs import TaskInput
from ..ports import Clock, CourseRepository, TaskRepository
from ..records import TaskRecord, course_record, task_record


class TaskService:
    """Use cases for tasks, homework, assignments and exams."""

    def __init__(self, tasks: TaskRepository, courses: CourseRepository, clock: Clock,
                 bus: ChangeBus):
        self._tasks = tasks
        self._courses = courses
        self._clock = clock
        self._bus = bus

    def groups(self, include_done: bool = False, course_id: int | None = None) -> list[TaskGroup]:
        """Tasks grouped by when they are due; empty groups are left out."""
        today = self._clock.today()
        by_id = {c.id: course_record(c) for c in self._courses.list()}
        buckets: dict[DueBucket, list[TaskItem]] = {b: [] for b in DueBucket}
        for t in self._tasks.list(include_done, course_id):
            buckets[t.bucket(today)].append(
                TaskItem(task_record(t), by_id.get(t.course_id), t.is_overdue(today)))
        return [TaskGroup(b, tuple(items)) for b, items in buckets.items() if items]

    def _task(self, task_id: int) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise NotFound(f"Task {task_id} does not exist.")
        return task

    def task(self, task_id: int) -> TaskRecord:
        return task_record(self._task(task_id))

    def save(self, task_id: int | None, data: TaskInput) -> int:
        """Create a task, or change one. Only the fields in `data` change, so a task
        imported from the school register keeps its link to it."""
        task = Task("") if task_id is None else self._task(task_id)
        task.title = data.title.strip()
        task.kind = TaskKind(data.kind)  # accepts "homework" as well as TaskKind.HOMEWORK
        task.course_id, task.due, task.details, task.done = (
            data.course_id, data.due, data.details, data.done)
        task.validate()
        if task.id is None:
            task.id = self._tasks.add(task)
        else:
            self._tasks.update(task)
        self._bus.publish(Topic.TASKS)
        return task.id

    def set_done(self, task_id: int, done: bool):
        task = self._task(task_id)
        task.done = done
        self._tasks.update(task)
        self._bus.publish(Topic.TASKS)

    def delete(self, task_id: int):
        self._tasks.delete(task_id)
        self._bus.publish(Topic.TASKS)
