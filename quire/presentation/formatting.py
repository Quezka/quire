"""User-facing text for domain values."""
from __future__ import annotations

from datetime import date, datetime

from ..domain import DueBucket, TaskKind, TimeRange
from .i18n import (
    N_, Translated, _, month_of, month_short, weekday_name, weekday_short,
)
from .i18n import plural as i18n_plural

KIND_LABELS = Translated({
    TaskKind.TASK: N_("Task"),
    TaskKind.HOMEWORK: N_("Homework"),
    TaskKind.ASSIGNMENT: N_("Assignment"),
    TaskKind.EXAM: N_("Exam / test"),
    TaskKind.READING: N_("Reading"),
})

BUCKET_LABELS = Translated({
    DueBucket.OVERDUE: N_("Overdue"),
    DueBucket.TODAY: N_("Today"),
    DueBucket.UPCOMING: N_("Next 7 days"),
    DueBucket.LATER: N_("Later"),
    DueBucket.UNDATED: N_("No date"),
    DueBucket.DONE: N_("Completed"),
})


def fmt_min(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_range(t: TimeRange) -> str:
    return f"{fmt_min(t.start)}–{fmt_min(t.end)}"


def _capitalised(text: str) -> str:
    # Russian day names are lower case mid-sentence; as a heading they start with a capital.
    return text[:1].upper() + text[1:]


def long_date(d: date) -> str:
    # Built by hand: "%-d" is not portable to Windows, and names must be translatable.
    return _capitalised(f"{weekday_name(d)}, {d.day} {month_of(d)}")


def relative_date(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return _("Today")
    if delta == 1:
        return _("Tomorrow")
    if delta == -1:
        return _("Yesterday")
    if 1 < delta < 7:
        return _capitalised(weekday_name(d))
    text = f"{weekday_short(d)} {d.day} {month_short(d)}"
    return text if d.year == today.year else f"{text} {d.year}"


def was_due(d: date, today: date) -> str:
    """"was due yesterday" / "was due Mon 21 Sep"."""
    when = relative_date(d, today)
    if when == _("Yesterday"):
        when = when.lower()
    return _("was due {when}").format(when=when)


def relative_timestamp(ts: datetime | None, today: date) -> str:
    if ts is None:
        return ""
    if ts.date() == today:
        return f"{_('Today')} {ts:%H:%M}"
    return relative_date(ts.date(), today)


def fmt_duration(minutes: int) -> str:
    hours, rest = divmod(int(minutes), 60)
    if not hours:
        return _("{minutes} min").format(minutes=rest)
    if rest:
        return _("{hours} h {minutes:02d}").format(hours=hours, minutes=rest)
    return _("{hours} h").format(hours=hours)


def money(value: float) -> str:
    """An amount in the chosen currency, with the system's number format."""
    from PySide6.QtCore import QLocale

    from .preferences import preferences

    return QLocale.system().toCurrencyString(value, preferences().currency_symbol())


def fmt_days(weekdays) -> str:
    """Compact weekday list: "Mon–Fri", "Every day", "Tue, Thu, Sat"."""
    days = sorted(set(weekdays))
    if days == list(range(7)):
        return _("Every day")
    if days == [5, 6]:
        return _("Weekends")
    short = [weekday_short(date(2026, 9, 21 + d)) for d in days]  # 21 Sep 2026 is a Monday
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{short[0]}–{short[-1]}"
    return ", ".join(short)


def pay_text(gross: float | None, net: float | None) -> str:
    """"€40.00" or "€40.00 gross · €32.00 net" when something is withheld."""
    if gross is None:
        return ""
    if net is None or abs(net - gross) < 0.005:
        return money(gross)
    return _("{gross} gross · {net} net").format(gross=money(gross), net=money(net))


def plural(n: int, word: str, suffix: str = "s") -> str:
    return i18n_plural(n, word, suffix)
