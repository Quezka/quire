from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ...domain import COURSE_COLORS, Course, Grade, Lesson, NotFound, Subject, Task, average
from ..bus import ChangeBus, Topic
from ..errors import AuthenticationError, NotConnected, RegisterError
from ..ports import (
    Clock, CourseRepository, CredentialStore, Credentials, KeyValueStore, RegisterAccount,
    RegisterSnapshot, RemoteAssignment, SchoolRecordRepository, SchoolRegister, TaskRepository,
)

ASSIGNMENTS_PAST_DAYS = 30
ASSIGNMENTS_FUTURE_DAYS = 120
LESSON_DAYS = 21
TITLE_LENGTH = 90


def tidy_subject(name: str) -> str:
    """Registers shout ("MATEMATICA"); store names in sentence case."""
    name = " ".join(name.split())
    return name.capitalize() if name.isupper() else name


def tidy_person(name: str) -> str:
    name = " ".join(name.split())
    return name.title() if name.isupper() else name


def assignment_title(item: RemoteAssignment) -> str:
    first = next((line.strip() for line in item.text.splitlines() if line.strip()), "")
    title = first or tidy_subject(item.subject_name) or "School assignment"
    return title if len(title) <= TITLE_LENGTH else title[: TITLE_LENGTH - 1].rstrip() + "…"


@dataclass(frozen=True)
class SchoolStatus:
    register: str
    connected: bool
    username: str = ""
    student_name: str = ""
    last_sync: datetime | None = None


@dataclass(frozen=True)
class SyncReport:
    first_sync: bool
    new_tasks: tuple[Task, ...] = ()
    updated_tasks: tuple[Task, ...] = ()
    removed_tasks: int = 0
    new_grades: tuple[Grade, ...] = ()
    lessons: int = 0
    courses_created: int = 0
    problems: tuple[str, ...] = ()  # parts of the register that couldn't be synced

    @property
    def has_news(self) -> bool:
        return bool(self.new_tasks or self.updated_tasks or self.new_grades)


@dataclass(frozen=True)
class SubjectLink:
    """A register subject and the local course it is linked to, if any."""

    subject: Subject
    course: Course | None


@dataclass(frozen=True)
class SubjectGrades:
    subject: str
    course: Course | None
    grades: tuple[Grade, ...]  # newest first
    average: float | None


class SchoolSyncService:
    """Use cases for mirroring a school register (e.g. Classeviva) into Quire.

    `fetch()` only talks to the register and the credential store, so the UI can
    run it on a worker thread; `apply()` writes locally and must run on the thread
    that owns the database.
    """

    def __init__(self, register: SchoolRegister, credentials: CredentialStore,
                 courses: CourseRepository, tasks: TaskRepository,
                 records: SchoolRecordRepository, settings: KeyValueStore, clock: Clock,
                 bus: ChangeBus):
        self._register = register
        self._credentials = credentials
        self._courses = courses
        self._tasks = tasks
        self._records = records
        self._settings = settings
        self._clock = clock
        self._bus = bus
        self._source = register.name.lower()
        self.last_report: SyncReport | None = None

    def _key(self, name: str) -> str:
        return f"{self._source}.{name}"

    def _external(self, kind: str, remote_id: str) -> str:
        return f"{self._source}:{kind}:{remote_id}"

    # ---- account ------------------------------------------------------------

    def status(self) -> SchoolStatus:
        username = self._settings.get(self._key("username")) or ""
        last = self._settings.get(self._key("last_sync"))
        return SchoolStatus(
            register=self._register.name,
            connected=bool(username),
            username=username,
            student_name=self._settings.get(self._key("student")) or "",
            last_sync=datetime.fromisoformat(last) if last else None,
        )

    def connect(self, username: str, password: str) -> RegisterAccount:
        """Check the credentials with the register, then remember them."""
        credentials = Credentials(username.strip(), password)
        account = self._register.login(credentials)
        self._credentials.save(credentials)
        self._settings.set(self._key("username"), credentials.username)
        self._settings.set(self._key("student"), account.student_name)
        self._bus.publish(Topic.SCHOOL)
        return account

    def disconnect(self):
        """Forget the account. Imported tasks, grades and lessons stay."""
        self._credentials.clear()
        for name in ("username", "student", "last_sync"):
            self._settings.set(self._key(name), None)
        self.last_report = None
        self._bus.publish(Topic.SCHOOL)

    # ---- sync ---------------------------------------------------------------

    def fetch(self) -> RegisterSnapshot:
        credentials = self._credentials.load()
        if credentials is None:
            raise NotConnected(f"Connect your {self._register.name} account first.")
        today = self._clock.today()
        assignment_window = (today - timedelta(days=ASSIGNMENTS_PAST_DAYS),
                             today + timedelta(days=ASSIGNMENTS_FUTURE_DAYS))
        lesson_window = (today - timedelta(days=LESSON_DAYS), today)
        account = self._register.login(credentials)
        problems: list[str] = []

        def part(label: str, call):
            # One broken endpoint shouldn't stop the rest of the sync.
            try:
                return tuple(call())
            except AuthenticationError:
                raise
            except RegisterError as e:
                problems.append(f"{label}: {e}")
                return None

        snapshot = RegisterSnapshot(
            account=account,
            subjects=part("Subjects", self._register.subjects),
            assignments=part("Homework and tests",
                             lambda: self._register.assignments(*assignment_window)),
            grades=part("Grades", self._register.grades),
            lessons=part("Lesson topics", lambda: self._register.lessons(*lesson_window)),
            assignment_window=assignment_window,
            lesson_window=lesson_window,
            problems=tuple(problems),
        )
        if len(problems) == 4:
            raise RegisterError("Couldn't sync anything from "
                                f"{self._register.name}. " + " ".join(problems))
        return snapshot

    def sync(self) -> SyncReport:
        return self.apply(self.fetch())

    def apply(self, snap: RegisterSnapshot) -> SyncReport:
        first_sync = self._settings.get(self._key("last_sync")) is None
        subject_ids, subject_names, created = self._sync_courses(snap)

        def course_for(subject_id, subject_name):
            return (subject_ids.get(subject_id)
                    or subject_names.get(tidy_subject(subject_name).casefold()))

        new_tasks, updated_tasks, removed = [], [], 0
        if snap.assignments is not None:
            new_tasks, updated_tasks, removed = self._sync_assignments(snap, course_for)

        new_grades: tuple[Grade, ...] = ()
        if snap.grades is not None:
            known = {g.external_id for g in self._records.grades()}
            grades = [
                Grade(self._external("grade", g.id), tidy_subject(g.subject_name), g.day,
                      g.display, g.value, g.component, g.period, g.notes, g.cancelled,
                      course_for(g.subject_id, g.subject_name))
                for g in snap.grades
            ]
            self._records.replace_grades(grades)
            new_grades = tuple(g for g in grades if g.external_id not in known)

        lessons = []
        if snap.lessons is not None:
            lessons = [
                Lesson(self._external("lesson", l.id), l.day, tidy_subject(l.subject_name),
                       l.topic, tidy_person(l.teacher), l.hour,
                       course_for(l.subject_id, l.subject_name))
                for l in snap.lessons
            ]
            if snap.lesson_window:
                self._records.replace_lessons(*snap.lesson_window, lessons)

        self._settings.set(self._key("student"), snap.account.student_name)
        self._settings.set(self._key("last_sync"), self._clock.now().isoformat(timespec="seconds"))

        report = SyncReport(first_sync, tuple(new_tasks), tuple(updated_tasks), removed,
                            new_grades, len(lessons), created, snap.problems)
        self.last_report = report
        if created:
            self._bus.publish(Topic.COURSES)
        self._bus.publish(Topic.TASKS)
        self._bus.publish(Topic.SCHOOL)
        return report

    def _sync_courses(self, snap: RegisterSnapshot):
        """Match register subjects to local courses, creating any that are missing."""
        if snap.subjects:
            self._records.replace_subjects([
                Subject(self._external("subject", s.id), tidy_subject(s.name),
                        tuple(tidy_person(t) for t in s.teachers if t))
                for s in snap.subjects])
        courses = self._courses.list()
        by_external = {c.external_id: c for c in courses if c.external_id}
        by_name = {c.name.casefold(): c for c in courses}
        used_colors = {c.color for c in courses}
        subject_ids: dict[str, int] = {}
        created = 0
        for subject in snap.subjects or ():
            external = self._external("subject", subject.id)
            name = tidy_subject(subject.name)
            teacher = ", ".join(tidy_person(t) for t in subject.teachers)
            course = by_external.get(external) or by_name.get(name.casefold())
            if course is None:
                color = next((c for c in COURSE_COLORS if c not in used_colors),
                             COURSE_COLORS[len(used_colors) % len(COURSE_COLORS)])
                used_colors.add(color)
                course = Course(name, teacher, color=color, external_id=external)
                course.id = self._courses.add(course)
                by_name[name.casefold()] = course
                created += 1
            elif course.external_id != external or (teacher and not course.teacher):
                course.external_id = external
                course.teacher = course.teacher or teacher
                self._courses.update(course)
            subject_ids[subject.id] = course.id
        return subject_ids, {k: c.id for k, c in by_name.items()}, created

    def _sync_assignments(self, snap: RegisterSnapshot, course_for):
        prefix = self._external("agenda", "")
        existing = {t.external_id: t for t in self._tasks.by_external_prefix(prefix)}
        seen, new, updated = set(), [], []
        for item in snap.assignments:
            external = prefix + item.id
            seen.add(external)
            details = item.text.strip()
            if item.author:
                details += f"\n\n— {tidy_person(item.author)}"
            fields = dict(title=assignment_title(item), kind=item.kind, due=item.day,
                          course_id=course_for(item.subject_id, item.subject_name),
                          details=details)
            task = existing.get(external)
            if task is None:
                task = Task(**fields, external_id=external)
                task.id = self._tasks.add(task)
                new.append(task)
            elif any(getattr(task, k) != v for k, v in fields.items()):
                for k, v in fields.items():  # keeps the user's done/not-done state
                    setattr(task, k, v)
                self._tasks.update(task)
                updated.append(task)

        removed = 0
        if snap.assignment_window:
            first, last = snap.assignment_window
            for external, task in existing.items():
                # Teacher deleted it: drop it, unless the student already ticked it off.
                if (external not in seen and not task.done and task.due
                        and first <= task.due <= last):
                    self._tasks.delete(task.id)
                    removed += 1
        return new, updated, removed

    # ---- linking --------------------------------------------------------------

    def subject_links(self) -> list[SubjectLink]:
        """Subjects seen in the last sync, each with the course it feeds into."""
        by_external = {c.external_id: c for c in self._courses.list() if c.external_id}
        return [SubjectLink(s, by_external.get(s.external_id)) for s in self._records.subjects()]

    def link_course(self, course_id: int, subject_id: str | None):
        """Make `course_id` the course a register subject syncs into (None unlinks).

        A course the sync created for that subject is folded into this one: its
        imported homework, grades, lesson topics and notes move over, and the empty
        duplicate is deleted. A course that has class times of its own is only
        unlinked, never deleted.
        """
        course = self._courses.get(course_id)
        if course is None:
            raise NotFound(f"Course {course_id} does not exist.")
        if course.external_id == subject_id:
            return
        if subject_id is not None:
            subject = next((s for s in self._records.subjects() if s.external_id == subject_id),
                           None)
            if subject is None:
                raise NotFound("That subject isn't in the last sync. Sync again and retry.")
            previous = next((c for c in self._courses.list()
                             if c.external_id == subject_id and c.id != course_id), None)
            if previous is not None:
                if previous.slots:
                    previous.external_id = None
                    self._courses.update(previous)
                else:
                    self._courses.merge_into(previous.id, course_id)
            if not course.teacher and subject.teachers:
                course.teacher = ", ".join(subject.teachers)
        course.external_id = subject_id
        self._courses.update(course)
        self._bus.publish(Topic.COURSES)
        self._bus.publish(Topic.TASKS)
        self._bus.publish(Topic.SCHOOL)

    # ---- queries --------------------------------------------------------------

    def grades_by_subject(self) -> list[SubjectGrades]:
        courses = {c.id: c for c in self._courses.list()}
        groups: dict[str, list[Grade]] = {}
        for g in self._records.grades():
            groups.setdefault(g.subject, []).append(g)
        result = []
        for subject in sorted(groups, key=str.casefold):
            grades = sorted(groups[subject], key=lambda g: g.day, reverse=True)
            course = next((courses.get(g.course_id) for g in grades if g.course_id), None)
            result.append(SubjectGrades(subject, course, tuple(grades), average(grades)))
        return result

    def overall_average(self) -> float | None:
        return average(self._records.grades())

    def recent_lessons(self, days: int = 14) -> list[Lesson]:
        today = self._clock.today()
        lessons = self._records.lessons_between(today - timedelta(days=days), today)
        return sorted(lessons, key=lambda l: (l.day, l.hour), reverse=True)
