"""Core entities and business rules.

Pure Python: nothing here knows about Qt, SQLite or any other framework.
Times of day are minutes after midnight; weekdays follow Python's
convention (0 = Monday ... 6 = Sunday).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum

from .errors import ValidationError

MINUTES_PER_DAY = 24 * 60
UPCOMING_DAYS = 7
COURSE_COLORS = (
    "#4f7cff", "#e5484d", "#30a46c", "#f5a524", "#8e4ec6",
    "#12a594", "#e93d82", "#f76b15", "#0090ff", "#978365",
)


@dataclass(frozen=True)
class TimeRange:
    start: int
    end: int

    def __post_init__(self):
        if not (0 <= self.start < MINUTES_PER_DAY and 0 < self.end <= MINUTES_PER_DAY):
            raise ValidationError("Times must fall within a single day.")
        if self.end <= self.start:
            raise ValidationError("The end time must be after the start time.")

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class ClassSlot:
    """One weekly meeting of a course."""

    weekday: int
    time: TimeRange
    room: str = ""

    def __post_init__(self):
        if not 0 <= self.weekday <= 6:
            raise ValidationError("Weekday must be between Monday and Sunday.")


@dataclass
class Course:
    name: str
    teacher: str = ""
    room: str = ""
    color: str = "#4f7cff"
    slots: list[ClassSlot] = field(default_factory=list)
    id: int | None = None
    external_id: str | None = None  # set when the course came from a school register

    def validate(self):
        if not self.name.strip():
            raise ValidationError("Give the course a name.")

    def slots_on(self, weekday: int) -> list[ClassSlot]:
        return sorted((s for s in self.slots if s.weekday == weekday), key=lambda s: s.time.start)

    def room_for(self, slot: ClassSlot) -> str:
        return slot.room or self.room

    def next_meeting_after(self, day: date) -> date | None:
        weekdays = {s.weekday for s in self.slots}
        for offset in range(1, 8):
            candidate = day + timedelta(days=offset)
            if candidate.weekday() in weekdays:
                return candidate
        return None


@dataclass
class Event:
    """A one-off entry in the day planner."""

    day: date
    time: TimeRange
    title: str
    details: str = ""
    color: str = "#8a8f98"
    id: int | None = None

    def validate(self):
        if not self.title.strip():
            raise ValidationError("Give the event a title.")


class TaskKind(str, Enum):
    TASK = "task"
    HOMEWORK = "homework"
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    READING = "reading"


class DueBucket(Enum):
    """When a task is due, relative to today. Declaration order is display order."""

    OVERDUE = "overdue"
    TODAY = "today"
    UPCOMING = "upcoming"
    LATER = "later"
    UNDATED = "undated"
    DONE = "done"


@dataclass
class Task:
    title: str
    kind: TaskKind = TaskKind.TASK
    course_id: int | None = None
    due: date | None = None
    done: bool = False
    details: str = ""
    id: int | None = None
    external_id: str | None = None  # set when the task was imported from a school register

    def validate(self):
        if not self.title.strip():
            raise ValidationError("Give the task a title.")

    def is_overdue(self, today: date) -> bool:
        return not self.done and self.due is not None and self.due < today

    def bucket(self, today: date) -> DueBucket:
        if self.done:
            return DueBucket.DONE
        if self.due is None:
            return DueBucket.UNDATED
        if self.due < today:
            return DueBucket.OVERDUE
        if self.due == today:
            return DueBucket.TODAY
        if (self.due - today).days <= UPCOMING_DAYS:
            return DueBucket.UPCOMING
        return DueBucket.LATER


# ---- pictures in notes ---------------------------------------------------------------

IMAGE_SCHEME = "quire-image:"
# A picture travels to other devices as one sync record, and a record must stay well under
# the cloud's 1 MiB per document once encoded.
MAX_IMAGE_BYTES = 700_000
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
IMAGE_REF = re.compile(r"!\[([^\]\n]*)\]\(quire-image:([0-9a-f]{8,64})\)")


@dataclass
class NoteImage:
    """A picture shown in notes, referenced from Markdown as ![alt](quire-image:<uid>)."""

    uid: str
    mime: str
    data: bytes
    id: int | None = None

    def check(self):
        if self.mime not in IMAGE_TYPES:
            raise ValidationError("Notes can show PNG, JPEG, GIF and WebP pictures.")
        if not self.data:
            raise ValidationError("That picture is empty.")
        if len(self.data) > MAX_IMAGE_BYTES:
            raise ValidationError("That picture is too big to keep in a note (over 700 KB).")


def image_markdown(uid: str, alt: str = "") -> str:
    alt = " ".join(alt.replace("[", "(").replace("]", ")").split())
    return f"![{alt}]({IMAGE_SCHEME}{uid})"


def image_uids(body: str) -> list[str]:
    """The pictures a note shows, in order (each once)."""
    return list(dict.fromkeys(m.group(2) for m in IMAGE_REF.finditer(body)))


def _without_images(text: str) -> str:
    return IMAGE_REF.sub(lambda m: m.group(1), text)


def derive_note_title(body: str) -> str:
    """A note's title is its first non-empty line, minus markdown heading marks (a picture
    counts by its description)."""
    for line in body.splitlines():
        text = _without_images(line).strip().lstrip("#").strip()
        if text:
            return text[:120]
    return "Untitled"


def note_snippet(body: str, length: int = 90) -> str:
    """The start of a note's text after its title, as plain words: for the notes list."""
    lines = [line.strip() for line in _without_images(body).splitlines() if line.strip()]
    text = " ".join(lines[1:])
    text = re.sub(r"^#{1,6}\s+|(?<=\s)#{1,6}\s+", "", text)
    text = re.sub(r"[-*+]\s+\[[ xX]\]\s+|(?:^|(?<=\s))[-*+>]\s+|\*\*|__|`|~~", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?<![\w*])[*_](?=\S)(.+?)(?<=\S)[*_](?![\w*])", r"\1", text)
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


TOPIC_LENGTH = 60


def normalize_topic(text: str) -> str:
    """Topics group notes within a course; compare them without stray whitespace."""
    return " ".join(text.split())[:TOPIC_LENGTH]


@dataclass
class Note:
    body: str = ""
    course_id: int | None = None
    pinned: bool = False
    updated: datetime | None = None
    id: int | None = None
    topic: str = ""  # e.g. "Cell respiration" within Biology; "" means ungrouped
    notebook_id: int | None = None  # a note is filed in a class (course_id) or a notebook

    @property
    def title(self) -> str:
        return derive_note_title(self.body)


@dataclass
class Notebook:
    """A group of notes that isn't a class: "Ideas", "Trips", a project."""

    name: str
    color: str = "#8a8f98"
    id: int | None = None

    def validate(self):
        if not self.name.strip():
            raise ValidationError("Give the notebook a name.")


@dataclass
class Grade:
    """A mark published by a teacher on the school register."""

    external_id: str
    subject: str
    day: date
    display: str  # as the school shows it, e.g. "7½", "8-", "ass"
    value: float | None = None  # numeric value, when the mark has one
    component: str = ""  # e.g. "Scritto", "Orale"
    period: str = ""
    notes: str = ""
    cancelled: bool = False
    course_id: int | None = None

    @property
    def counts(self) -> bool:
        return self.value is not None and not self.cancelled


PASS_MARK = 6.0  # on the Italian 1-10 scale Classeviva uses, below 6 is a fail


def average(grades: list[Grade]) -> float | None:
    """Mean of the marks that count; None when there are none."""
    values = [g.value for g in grades if g.counts]
    return round(sum(values) / len(values), 2) if values else None


@dataclass
class Lesson:
    """One lesson as recorded on the school register, with its topic."""

    external_id: str
    day: date
    subject: str
    topic: str = ""
    teacher: str = ""
    hour: int = 0  # position in the school day (1st hour, 2nd hour, ...)
    course_id: int | None = None


@dataclass(frozen=True)
class Subject:
    """A subject as the school register names it; courses can be linked to one."""

    external_id: str
    name: str
    teachers: tuple[str, ...] = ()


@dataclass
class Job:
    """Somewhere the student works shifts."""

    name: str
    color: str = "#0090ff"
    hourly_rate: float | None = None  # gross, in the user's currency; None if not tracked
    id: int | None = None
    # Every weekly pattern the job has had, including ended ones (kept for history).
    schedule: list["ShiftPattern"] = field(default_factory=list)
    # Share of gross pay withheld for tax and contributions, in percent (0-99.99).
    deductions: float = 0.0

    def validate(self):
        if not self.name.strip():
            raise ValidationError("Give the job a name.")
        if self.hourly_rate is not None and self.hourly_rate < 0:
            raise ValidationError("The hourly rate can't be negative.")
        if not 0 <= self.deductions < 100:
            raise ValidationError("Tax and deductions must be between 0% and 100%.")
        for pattern in self.schedule:
            pattern.validate()

    def active_schedule(self, today: date) -> list["ShiftPattern"]:
        """Patterns that still apply from `today` on (the ones you'd edit)."""
        return sorted((p for p in self.schedule if p.until is None or p.until >= today),
                      key=lambda p: (p.weekday, p.start))


MAX_SHIFT_MINUTES = 16 * 60


def net_pay(gross: float | None, deductions: float) -> float | None:
    """Take-home pay once `deductions` percent is withheld."""
    if gross is None:
        return None
    return round(gross * (1 - deductions / 100), 2)


@dataclass
class Shift:
    """One work shift. It may run past midnight into the next day."""

    job_id: int
    day: date
    start: int  # minutes after midnight on `day`
    duration: int  # minutes, including the break
    break_minutes: int = 0
    notes: str = ""
    id: int | None = None
    recurring: bool = False  # an occurrence of the job's weekly schedule, not stored

    def validate(self):
        _check_shift_times(self.start, self.duration, self.break_minutes)

    @classmethod
    def between(cls, job_id: int, day: date, start: int, end: int, **fields) -> "Shift":
        """Build a shift from clock times; an end at or before the start means next day."""
        duration = end - start if end > start else end + MINUTES_PER_DAY - start
        return cls(job_id, day, start, duration, **fields)

    @property
    def end(self) -> int:
        """Minutes after midnight on `day`; above 1440 when the shift ends the next day."""
        return self.start + self.duration

    @property
    def ends_next_day(self) -> bool:
        return self.end > MINUTES_PER_DAY

    @property
    def paid_minutes(self) -> int:
        return self.duration - self.break_minutes

    def pay(self, hourly_rate: float | None) -> float | None:
        if hourly_rate is None:
            return None
        return round(self.paid_minutes / 60 * hourly_rate, 2)

    def segments(self) -> list[tuple[date, TimeRange]]:
        """The parts of the shift on each calendar day it touches."""
        if not self.ends_next_day:
            return [(self.day, TimeRange(self.start, self.end))]
        return [(self.day, TimeRange(self.start, MINUTES_PER_DAY)),
                (self.day + timedelta(days=1), TimeRange(0, self.end - MINUTES_PER_DAY))]

    def overlaps(self, day: date, time: TimeRange) -> bool:
        return any(d == day and seg.start < time.end and time.start < seg.end
                   for d, seg in self.segments())


def _check_shift_times(start: int, duration: int, break_minutes: int):
    if not 0 <= start < MINUTES_PER_DAY:
        raise ValidationError("The shift must start within the day.")
    if not 0 < duration <= MAX_SHIFT_MINUTES:
        raise ValidationError("A shift must last between a minute and 16 hours.")
    if not 0 <= break_minutes < duration:
        raise ValidationError("The break must be shorter than the shift.")


@dataclass
class ShiftPattern:
    """A shift that repeats every week, like a class in the school timetable.

    `since`/`until` bound the weeks it applies to, so changing a schedule
    doesn't rewrite the hours already worked.
    """

    weekday: int
    start: int
    duration: int
    break_minutes: int = 0
    since: date | None = None
    until: date | None = None
    id: int | None = None

    @classmethod
    def between(cls, weekday: int, start: int, end: int, break_minutes: int = 0,
                **fields) -> "ShiftPattern":
        duration = end - start if end > start else end + MINUTES_PER_DAY - start
        return cls(weekday, start, duration, break_minutes, **fields)

    def validate(self):
        if not 0 <= self.weekday <= 6:
            raise ValidationError("Weekday must be between Monday and Sunday.")
        _check_shift_times(self.start, self.duration, self.break_minutes)
        if self.since and self.until and self.until < self.since:
            raise ValidationError("A repeating shift can't end before it starts.")

    @property
    def key(self) -> tuple[int, int, int, int]:
        """What makes two patterns the same shift."""
        return self.weekday, self.start, self.duration, self.break_minutes

    def occurs_on(self, day: date) -> bool:
        return (day.weekday() == self.weekday
                and (self.since is None or day >= self.since)
                and (self.until is None or day <= self.until))

    def shift_on(self, job_id: int, day: date) -> Shift:
        return Shift(job_id, day, self.start, self.duration, self.break_minutes,
                     recurring=True)


WORK_DAYS = (0, 1, 2, 3, 4)
EVERY_DAY = (0, 1, 2, 3, 4, 5, 6)


def work_shifts(jobs: list[Job], one_off: list[Shift], skipped: set[tuple[int, date, int]],
                first: date, last: date) -> list[Shift]:
    """All shifts starting on days first..last: one-off shifts plus weekly-schedule
    occurrences, minus the occurrences the user skipped (job id, day, start)."""
    result = [s for s in one_off if first <= s.day <= last]
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        for job in jobs:
            for pattern in job.schedule:
                if pattern.occurs_on(day) and (job.id, day, pattern.start) not in skipped:
                    result.append(pattern.shift_on(job.id, day))
    return sorted(result, key=lambda s: (s.day, s.start))


def reschedule(current: list[ShiftPattern], wanted: list[ShiftPattern],
               this_week: date) -> list[ShiftPattern]:
    """Apply a new weekly schedule from `this_week` (a Monday) on.

    Unchanged patterns are kept as they are. Patterns that are no longer wanted end
    the Sunday before `this_week`, or disappear entirely if they started this week.
    New ones start `this_week`. Patterns that ended earlier stay for history.
    """
    active = [p for p in current if p.until is None or p.until >= this_week]
    wanted_keys = {p.key for p in wanted}
    active_keys = {p.key for p in active}
    result = [p for p in current if p not in active]
    for pattern in active:
        if pattern.key in wanted_keys:
            result.append(pattern)
        elif pattern.since is None or pattern.since < this_week:
            result.append(ShiftPattern(pattern.weekday, pattern.start, pattern.duration,
                                       pattern.break_minutes, pattern.since,
                                       this_week - timedelta(days=1), pattern.id))
        # else: it only ever applied from this week on, so it simply goes away
    for pattern in wanted:
        if pattern.key not in active_keys:
            active_keys.add(pattern.key)
            result.append(ShiftPattern(pattern.weekday, pattern.start, pattern.duration,
                                       pattern.break_minutes, since=this_week))
    return result
