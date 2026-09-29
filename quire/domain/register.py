"""School-register records beyond grades and lessons: absences, the noticeboard, textbooks
and documents, plus the arithmetic Quire does on them."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# Italian rule: missing more than a quarter of the year's lesson hours can mean repeating it
# (schools grant exceptions, e.g. for health reasons).
ABSENCE_LIMIT = 0.25
GRADE_MIN, GRADE_MAX = 1.0, 10.0


class AbsenceKind(str, Enum):
    ABSENT = "absent"  # the whole day
    LATE = "late"  # came in after the first hour
    SHORT_LATE = "short_late"  # a few minutes late: no hours lost
    EARLY_EXIT = "early_exit"


@dataclass
class Absence:
    external_id: str
    day: date
    kind: AbsenceKind
    hour: int | None = None  # the lesson hour of a late entry or early exit
    justified: bool = False
    reason: str = ""
    hours: int = 0  # hours the register itself counted, when it says (0: unknown)
    # The hour you entered yourself, for when the school recorded the late entry or early
    # exit without one (Classeviva then sends no hour at all).
    own_hour: int | None = None

    @property
    def known_hour(self) -> int | None:
        return self.hour if self.hour is not None else self.own_hour

    def hours_missed(self, hours_that_day: int) -> int:
        """Lesson hours lost, given how many hours that day has (from the timetable)."""
        if self.hours:
            return self.hours
        if self.kind is AbsenceKind.ABSENT:
            return hours_that_day
        if self.kind is AbsenceKind.LATE:  # "entered at the 2nd hour": missed the 1st
            return max((self.known_hour or 2) - 1, 0)
        if self.kind is AbsenceKind.EARLY_EXIT:  # "left at the 5th hour": missed 5th onwards
            return max(hours_that_day - (self.known_hour or hours_that_day) + 1, 0)
        return 0


@dataclass(frozen=True)
class NoticeAttachment:
    number: int
    file_name: str


@dataclass
class Notice:
    """A circular or announcement on the school noticeboard."""

    external_id: str
    code: str  # the register's event code and publication id, needed to open it
    pub_id: str
    title: str
    category: str
    published: date
    valid_until: date | None = None
    read: bool = False
    attachments: tuple[NoticeAttachment, ...] = field(default_factory=tuple)


@dataclass
class Book:
    isbn: str
    title: str
    subject: str
    author: str = ""
    publisher: str = ""
    volume: str = ""
    price: float | None = None
    to_buy: bool = False
    owned: bool = False
    new_adoption: bool = False


class DocumentKind(str, Enum):
    DOCUMENT = "document"  # a file the school published for the student
    REPORT = "report"  # a term report card (pagella)


@dataclass
class SchoolDocument:
    external_id: str  # the register's id (a hash for documents)
    title: str
    kind: DocumentKind
    link: str = ""  # reports open as a web page


def lesson_hours(minutes: int) -> int:
    """Italian "ore" in a class period: a 50-60 minute period is one, a double period two."""
    return max(1, round(minutes / 60)) if minutes > 0 else 0


def needed_grade(values: list[float], target: float, tests: int = 1) -> float:
    """The mark needed on each of the next `tests` tests for the average to reach `target`.

    May fall below the lowest mark (the target is safe whatever happens) or above the highest
    (it can't be reached with that many tests); callers say so.
    """
    count = len(values)
    needed = (target * (count + tests) - sum(values)) / tests
    return math.ceil(needed * 4 - 1e-9) / 4  # marks go in quarters (6+, 6½, 6-…): round up


def running_average(points: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """(day, average of every mark up to that day), one point per day, oldest first."""
    result: list[tuple[date, float]] = []
    total = 0.0
    for n, (day, value) in enumerate(sorted(points), 1):
        total += value
        entry = (day, round(total / n, 2))
        if result and result[-1][0] == day:
            result[-1] = entry
        else:
            result.append(entry)
    return result
