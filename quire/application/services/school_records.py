from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ...domain import PASS_MARK, Grade, Task, TaskKind, average
from ..dto import TaskItem
from ..ports import Clock, CourseRepository, SchoolRecordRepository, TaskRepository
from ..records import (
    CourseRecord, GradeRecord, LessonRecord, SubjectRecord, course_record, grade_record,
    lesson_record, subject_record, task_record,
)


@dataclass(frozen=True)
class SubjectLink:
    """A register subject and the local course it is linked to, if any."""

    subject: SubjectRecord
    course: CourseRecord | None


@dataclass(frozen=True)
class SubjectGrades:
    subject: str
    course: CourseRecord | None
    grades: tuple[GradeRecord, ...]  # newest first
    average: float | None


@dataclass(frozen=True)
class SchoolOverview:
    """The numbers at the top of the School page."""

    average: float | None
    grade_count: int
    next_test: TaskItem | None
    homework_due_this_week: int
    next_homework: TaskItem | None
    below_pass: tuple[SubjectGrades, ...]  # subjects averaging under the pass mark


class SchoolRecordsService:
    """Read-only use cases over what was synced from the school register:
    grades and averages, terms, homework and tests, lesson topics, subjects."""

    def __init__(self, courses: CourseRepository, tasks: TaskRepository,
                 records: SchoolRecordRepository, clock: Clock, source: str):
        self._courses = courses
        self._tasks = tasks
        self._records = records
        self._clock = clock
        self._source = source  # prefix of the register's sync ids, e.g. "classeviva"

    def _course_records(self) -> dict[int, CourseRecord]:
        return {c.id: course_record(c) for c in self._courses.list()}

    def subject_links(self) -> list[SubjectLink]:
        """Subjects seen in the last sync, each with the course it feeds into."""
        by_external = {c.external_id: course_record(c) for c in self._courses.list()
                       if c.external_id}
        return [SubjectLink(subject_record(s), by_external.get(s.external_id))
                for s in self._records.subjects()]

    def periods(self) -> list[str]:
        """School terms the grades belong to (e.g. "Trimestre"), in calendar order."""
        first_seen: dict[str, date] = {}
        for g in self._records.grades():
            if g.period and (g.period not in first_seen or g.day < first_seen[g.period]):
                first_seen[g.period] = g.day
        return sorted(first_seen, key=first_seen.get)

    def _grades(self, period: str | None) -> list[Grade]:
        return [g for g in self._records.grades() if period is None or g.period == period]

    def grades_by_subject(self, period: str | None = None) -> list[SubjectGrades]:
        """Grades per subject, optionally for one term only."""
        courses = self._course_records()
        groups: dict[str, list[Grade]] = {}
        for g in self._grades(period):
            groups.setdefault(g.subject, []).append(g)
        result = []
        for subject in sorted(groups, key=str.casefold):
            grades = sorted(groups[subject], key=lambda g: g.day, reverse=True)
            course = next((courses.get(g.course_id) for g in grades if g.course_id), None)
            result.append(SubjectGrades(subject, course, tuple(grade_record(g) for g in grades),
                                        average(grades)))
        return result

    def overall_average(self, period: str | None = None) -> float | None:
        return average(self._grades(period))

    def _register_tasks(self) -> list[Task]:
        return self._tasks.by_external_prefix(f"{self._source}:")

    def upcoming(self, days: int = 21) -> list[TaskItem]:
        """Homework and tests from the register that are still to do, soonest first."""
        today = self._clock.today()
        courses = self._course_records()
        tasks = [t for t in self._register_tasks()
                 if not t.done and t.due is not None and 0 <= (t.due - today).days <= days]
        tasks.sort(key=lambda t: (t.due, t.kind is not TaskKind.EXAM, t.title.casefold()))
        return [TaskItem(task_record(t), courses.get(t.course_id), False) for t in tasks]

    def agenda(self, include_done: bool = False, days_ahead: int = 60,
               done_days_back: int = 14) -> list[TaskItem]:
        """Everything the register assigned: overdue work, today and what's ahead.

        With `include_done`, work ticked off in the last `done_days_back` days too.
        """
        today = self._clock.today()
        courses = self._course_records()
        result = []
        for t in self._register_tasks():
            if t.due is None:
                continue
            ahead = (t.due - today).days
            if t.done:
                keep = include_done and -done_days_back <= ahead <= days_ahead
            else:
                keep = ahead <= days_ahead  # includes everything overdue
            if keep:
                result.append(t)
        result.sort(key=lambda t: (t.due, t.kind is not TaskKind.EXAM, t.title.casefold()))
        return [TaskItem(task_record(t), courses.get(t.course_id), t.is_overdue(today))
                for t in result]

    def overview(self, period: str | None = None) -> SchoolOverview:
        today = self._clock.today()
        soon = self.upcoming(days=60)
        tests = [i for i in soon if i.task.kind is TaskKind.EXAM]
        homework = [i for i in soon if i.task.kind is not TaskKind.EXAM]
        subjects = self.grades_by_subject(period)
        return SchoolOverview(
            average=self.overall_average(period),
            grade_count=sum(1 for s in subjects for g in s.grades if g.counts),
            next_test=tests[0] if tests else None,
            homework_due_this_week=sum(1 for i in homework if (i.task.due - today).days <= 6),
            next_homework=homework[0] if homework else None,
            below_pass=tuple(s for s in subjects
                             if s.average is not None and s.average < PASS_MARK),
        )

    def recent_lessons(self, days: int = 14) -> list[LessonRecord]:
        today = self._clock.today()
        lessons = self._records.lessons_between(today - timedelta(days=days), today)
        return [lesson_record(l)
                for l in sorted(lessons, key=lambda l: (l.day, l.hour), reverse=True)]
