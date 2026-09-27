from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ...domain import (
    ABSENCE_LIMIT, GRADE_MAX, GRADE_MIN, PASS_MARK, AbsenceKind, Grade, Task, TaskKind, average,
    lesson_hours, needed_grade, running_average,
)
from ..dto import TaskItem
from ..ports import Clock, CourseRepository, SchoolRecordRepository, TaskRepository
from ..records import (
    AbsenceRecord, BookRecord, CourseRecord, DocumentRecord, GradeRecord, LessonRecord,
    NoticeRecord, SubjectRecord, absence_record, book_record, course_record, document_record,
    grade_record, lesson_record, notice_record, subject_record, task_record,
)

SCHOOL_WEEKS = 33  # when the register has no calendar: a typical Italian school year


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


@dataclass(frozen=True)
class AbsenceSummary:
    items: tuple[AbsenceRecord, ...]  # newest first
    absent_days: int
    late_entries: int
    early_exits: int
    unjustified: int
    hours_missed: int
    school_hours: int  # lesson hours in the year (estimated); 0 without a timetable
    limit_hours: int  # the most that may be missed (a quarter of school_hours)

    @property
    def share(self) -> float | None:
        """Part of the year's hours missed so far (0..1), None when unknown."""
        return self.hours_missed / self.school_hours if self.school_hours else None

    @property
    def hours_left(self) -> int:
        return max(self.limit_hours - self.hours_missed, 0)


@dataclass(frozen=True)
class NeededGrade:
    """What the next test(s) must score for a subject's average to reach a target."""

    subject: str
    target: float
    tests: int
    mark: float  # needed on each of those tests
    average: float | None
    grade_count: int

    @property
    def already_safe(self) -> bool:  # even the lowest mark keeps the target
        return self.mark <= GRADE_MIN

    @property
    def reachable(self) -> bool:
        return self.mark <= GRADE_MAX


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

    # ---- absences ------------------------------------------------------------------

    def _hours_per_weekday(self) -> dict[int, int]:
        """Lesson hours on each weekday, from the timetable in Quire."""
        hours: dict[int, int] = {}
        for course in self._courses.list():
            for slot in course.slots:
                hours[slot.weekday] = hours.get(slot.weekday, 0) + lesson_hours(
                    slot.time.end - slot.time.start)
        return hours

    def absence_summary(self) -> AbsenceSummary:
        """Absences so far and how close they are to the limit of a quarter of the year.

        The year's hours are estimated from the register's calendar (days with lessons) and
        your timetable (hours on each weekday); without a timetable they're unknown.
        """
        per_day = self._hours_per_weekday()
        days = self._records.school_days()
        if days:
            school_hours = sum(per_day.get(d.weekday(), 0) for d in days)
        else:
            school_hours = sum(per_day.values()) * SCHOOL_WEEKS
        absences = sorted(self._records.absences(), key=lambda a: a.day, reverse=True)
        items = tuple(absence_record(a, per_day.get(a.day.weekday(), 0)) for a in absences)
        return AbsenceSummary(
            items,
            absent_days=sum(1 for a in absences if a.kind is AbsenceKind.ABSENT),
            late_entries=sum(1 for a in absences
                             if a.kind in (AbsenceKind.LATE, AbsenceKind.SHORT_LATE)),
            early_exits=sum(1 for a in absences if a.kind is AbsenceKind.EARLY_EXIT),
            unjustified=sum(1 for a in absences if not a.justified),
            hours_missed=sum(i.hours_missed for i in items),
            school_hours=school_hours,
            limit_hours=int(school_hours * ABSENCE_LIMIT),
        )

    # ---- noticeboard, textbooks, documents -----------------------------------------------

    def notices(self) -> list[NoticeRecord]:
        return [notice_record(n) for n in self._records.notices()]

    def unread_notices(self) -> int:
        return sum(1 for n in self._records.notices() if not n.read)

    def books(self) -> list[BookRecord]:
        """Textbooks, grouped by subject."""
        return sorted((book_record(b) for b in self._records.books()),
                      key=lambda b: (b.subject.casefold(), b.title.casefold()))

    def documents(self) -> list[DocumentRecord]:
        return [document_record(d) for d in self._records.documents()]

    # ---- grade tools -----------------------------------------------------------------

    def _marks(self, subject: str, period: str | None) -> list[Grade]:
        return [g for g in self._grades(period) if g.subject == subject and g.counts]

    def needed(self, subject: str, target: float = PASS_MARK, tests: int = 1,
               period: str | None = None) -> NeededGrade:
        """The mark needed on the next `tests` tests for the subject's average to reach
        `target` (in one term, or the whole year)."""
        marks = self._marks(subject, period)
        values = [g.value for g in marks]
        return NeededGrade(subject, target, tests, needed_grade(values, target, tests),
                           average(marks), len(marks))

    def trend(self, subject: str | None = None,
              period: str | None = None) -> list[tuple[date, float]]:
        """How the average moved, mark by mark: one subject, or every subject together."""
        marks = [g for g in self._grades(period) if g.counts
                 and (subject is None or g.subject == subject)]
        return running_average([(g.day, g.value) for g in marks])
