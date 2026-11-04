"""Medicine tracking rules. Pure Python. It remembers what you told it to: it gives no medical advice."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .errors import ValidationError

MAX_DOSES_A_DAY = 12
EVERY_DAY: tuple[int, ...] = ()  # no weekdays chosen: every day
LATE_AFTER = 60  # minutes after the time before a dose counts as late
REMIND_FOR = 180  # minutes after the time it is still worth reminding


@dataclass
class Medicine:
    name: str
    dose: str = ""  # free text: "1 tablet", "5 ml"
    times: tuple[int, ...] = ()  # minutes after midnight
    weekdays: tuple[int, ...] = EVERY_DAY  # 0 = Monday
    active: bool = True
    notes: str = ""
    id: int | None = None

    def validate(self):
        if not self.name.strip():
            raise ValidationError("Give the medicine a name.")
        if len(self.times) > MAX_DOSES_A_DAY:
            raise ValidationError("That is more than 12 times a day.")
        if any(not 0 <= t < 24 * 60 for t in self.times) or len(set(self.times)) != len(self.times):
            raise ValidationError("Each time must be a different time of day.")
        if any(not 0 <= d <= 6 for d in self.weekdays):
            raise ValidationError("Choose days of the week.")

    def due_on(self, day: date) -> bool:
        return self.active and (not self.weekdays or day.weekday() in self.weekdays)


@dataclass
class DoseLog:
    """A dose you ticked: taken, or deliberately skipped. A planned dose with no log is still open."""

    medicine_id: int
    day: date
    planned: int  # the time of day it was planned for; -1 for an extra one, outside the plan
    taken: bool = True
    at: int = 0  # minutes after midnight when you ticked it
    id: int | None = None


@dataclass(frozen=True)
class PlannedDose:
    medicine: Medicine
    day: date
    planned: int
    log: DoseLog | None = field(default=None)

    @property
    def done(self) -> bool:
        return self.log is not None


def plan_for(day: date, medicines: list[Medicine], logs: list[DoseLog]) -> list[PlannedDose]:
    """Every dose of a day in time order, each with its log if it has one. A dose already logged shows even if
    the medicine has since been changed or stopped: what you took stays true."""
    by_key = {(log.medicine_id, log.planned): log for log in logs if log.day == day}
    plan = []
    known = {m.id: m for m in medicines}
    for m in medicines:
        if m.due_on(day):
            plan += [PlannedDose(m, day, t, by_key.pop((m.id, t), None)) for t in m.times]
    for (medicine_id, planned), log in by_key.items():
        if medicine_id in known:
            plan.append(PlannedDose(known[medicine_id], day, planned, log))
    return sorted(plan, key=lambda d: (d.planned if d.planned >= 0 else d.log.at if d.log else 0, d.medicine.name.lower()))


def is_late(dose: PlannedDose, minute: int) -> bool:
    return not dose.done and dose.planned >= 0 and minute > dose.planned + LATE_AFTER


def due_now(dose: PlannedDose, minute: int) -> bool:
    """Open, its time has come, and not so long ago that a reminder would be pointless."""
    return not dose.done and dose.planned >= 0 and dose.planned <= minute <= dose.planned + REMIND_FOR
