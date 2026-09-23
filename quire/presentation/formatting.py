"""User-facing text for domain values."""
from __future__ import annotations

from datetime import date, datetime

from ..domain import DueBucket, TaskKind, TimeRange

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

KIND_LABELS = {
    TaskKind.TASK: "Task",
    TaskKind.HOMEWORK: "Homework",
    TaskKind.ASSIGNMENT: "Assignment",
    TaskKind.EXAM: "Exam / test",
    TaskKind.READING: "Reading",
}

BUCKET_LABELS = {
    DueBucket.OVERDUE: "Overdue",
    DueBucket.TODAY: "Today",
    DueBucket.UPCOMING: "Next 7 days",
    DueBucket.LATER: "Later",
    DueBucket.UNDATED: "No date",
    DueBucket.DONE: "Completed",
}


def fmt_min(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_range(t: TimeRange) -> str:
    return f"{fmt_min(t.start)}–{fmt_min(t.end)}"


def long_date(d: date) -> str:
    # Built by hand: "%-d" is not portable to Windows.
    return f"{d:%A}, {d.day} {d:%B}"


def relative_date(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    if 1 < delta < 7:
        return f"{d:%A}"
    text = f"{d:%a} {d.day} {d:%b}"
    return text if d.year == today.year else f"{text} {d.year}"


def relative_timestamp(ts: datetime | None, today: date) -> str:
    if ts is None:
        return ""
    if ts.date() == today:
        return f"Today {ts:%H:%M}"
    return relative_date(ts.date(), today)


def fmt_duration(minutes: int) -> str:
    hours, rest = divmod(int(minutes), 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest:02d}" if rest else f"{hours} h"


def money(value: float) -> str:
    from PySide6.QtCore import QLocale

    return QLocale.system().toCurrencyString(value)


def plural(n: int, word: str, suffix: str = "s") -> str:
    return f"{n} {word}{'' if n == 1 else suffix}"
