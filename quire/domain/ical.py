"""Writing an agenda as an iCalendar file (RFC 5545). Pure Python. Times are floating (local), so they read the
same wherever the file is opened, like the times in Quire."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class CalendarEntry:
    uid: str  # stays the same for the same thing, so a calendar updates it instead of adding a copy
    title: str
    day: date
    start: int = 0  # minutes after midnight
    end: int = 24 * 60
    all_day: bool = False
    details: str = ""
    place: str = ""


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Lines of at most 75 bytes, continued with a leading space, never cutting a character in half."""
    out, current, size = [], "", 0
    for ch in line:
        width = len(ch.encode("utf-8"))
        if size + width > (75 if not out else 74):
            out.append(current)
            current, size = "", 0
        current += ch
        size += width
    out.append(current)
    return [out[0]] + [" " + piece for piece in out[1:]]


def _stamp(day: date, minute: int) -> str:
    moment = datetime(day.year, day.month, day.day) + timedelta(minutes=minute)
    return moment.strftime("%Y%m%dT%H%M%S")


def to_ics(entries: list[CalendarEntry], name: str, now: datetime) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Quezka//Quire//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_escape(name)}"]
    created = now.strftime("%Y%m%dT000000")  # by the day: the same agenda gives the same file, so nothing reloads
    for e in entries:
        lines += ["BEGIN:VEVENT", f"UID:{e.uid}", f"DTSTAMP:{created}", f"SUMMARY:{_escape(e.title)}"]
        if e.all_day:
            lines += [f"DTSTART;VALUE=DATE:{e.day.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(e.day + timedelta(days=1)).strftime('%Y%m%d')}"]
        else:
            lines += [f"DTSTART:{_stamp(e.day, e.start)}", f"DTEND:{_stamp(e.day, e.end)}"]
        if e.details:
            lines.append(f"DESCRIPTION:{_escape(e.details)}")
        if e.place:
            lines.append(f"LOCATION:{_escape(e.place)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(piece for line in lines for piece in _fold(line)) + "\r\n"
