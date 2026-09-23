from __future__ import annotations

from datetime import date, timedelta

from ...domain import Job, NotFound, Shift, TimeRange, ValidationError
from ..bus import ChangeBus, Topic
from ..dto import AgendaItem, ItemKind, JobTotal, ShiftItem, WorkSummary
from ..ports import Clock, JobRepository, ShiftRepository

MAX_REPEAT_WEEKS = 52


class WorkService:
    """Use cases for jobs and work shifts."""

    def __init__(self, jobs: JobRepository, shifts: ShiftRepository, clock: Clock,
                 bus: ChangeBus):
        self._jobs = jobs
        self._shifts = shifts
        self._clock = clock
        self._bus = bus

    # ---- jobs -------------------------------------------------------------------

    def jobs(self) -> list[Job]:
        return self._jobs.list()

    def job(self, job_id: int) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"Job {job_id} does not exist.")
        return job

    def save_job(self, job: Job) -> int:
        job.name = job.name.strip()
        job.validate()
        if job.id is None:
            job.id = self._jobs.add(job)
        else:
            self._jobs.update(job)
        self._bus.publish(Topic.WORK)
        return job.id

    def delete_job(self, job_id: int):
        """Delete a job together with all of its shifts."""
        self._jobs.delete(job_id)
        self._bus.publish(Topic.WORK)

    # ---- shifts -----------------------------------------------------------------

    def shift(self, shift_id: int) -> Shift:
        shift = self._shifts.get(shift_id)
        if shift is None:
            raise NotFound(f"Shift {shift_id} does not exist.")
        return shift

    def save_shift(self, shift: Shift, repeat_weeks: int = 0) -> list[int]:
        """Save a shift; for a new one, optionally copy it to the following weeks."""
        shift.validate()
        if self._jobs.get(shift.job_id) is None:
            raise ValidationError("Pick the job this shift is for.")
        if not 0 <= repeat_weeks <= MAX_REPEAT_WEEKS:
            raise ValidationError(f"Repeat for at most {MAX_REPEAT_WEEKS} weeks.")
        if shift.id is not None:
            if repeat_weeks:
                raise ValidationError("Only new shifts can be repeated.")
            self._shifts.update(shift)
            ids = [shift.id]
        else:
            shift.id = self._shifts.add(shift)
            ids = [shift.id]
            for week in range(1, repeat_weeks + 1):
                copy = Shift(shift.job_id, shift.day + timedelta(weeks=week), shift.start,
                             shift.duration, shift.break_minutes, shift.notes)
                ids.append(self._shifts.add(copy))
        self._bus.publish(Topic.WORK)
        return ids

    def delete_shift(self, shift_id: int):
        self._shifts.delete(shift_id)
        self._bus.publish(Topic.WORK)

    def shifts_between(self, first: date, last: date) -> list[ShiftItem]:
        jobs = {j.id: j for j in self._jobs.list()}
        return [ShiftItem(s, jobs.get(s.job_id))
                for s in sorted(self._shifts.starting_between(first, last),
                                key=lambda s: (s.day, s.start))]

    def upcoming(self, days: int = 28) -> list[ShiftItem]:
        """Shifts that haven't ended yet, soonest first."""
        now = self._clock.now()
        today = now.date()
        minute = now.hour * 60 + now.minute
        return [item for item in self.shifts_between(today - timedelta(days=1),
                                                     today + timedelta(days=days))
                if (item.shift.day - today).days * 1440 + item.shift.end > minute]

    def summary(self, first: date, last: date) -> WorkSummary:
        """Paid hours and estimated pay for shifts starting in [first, last]."""
        items = self.shifts_between(first, last)
        per_job: dict[int, list[ShiftItem]] = {}
        for item in items:
            per_job.setdefault(item.shift.job_id, []).append(item)
        totals = []
        for job_items in per_job.values():
            pays = [i.pay for i in job_items]
            totals.append(JobTotal(
                job_items[0].job, sum(i.shift.paid_minutes for i in job_items),
                None if any(p is None for p in pays) else round(sum(pays), 2)))
        totals.sort(key=lambda t: t.job.name.casefold() if t.job else "")
        known = [t.pay for t in totals if t.pay is not None]
        return WorkSummary(first, last, sum(t.minutes for t in totals),
                           round(sum(known), 2) if known else None, len(items), tuple(totals))

    def week_summary(self) -> WorkSummary:
        today = self._clock.today()
        monday = today - timedelta(days=today.weekday())
        return self.summary(monday, monday + timedelta(days=6))

    def month_summary(self) -> WorkSummary:
        today = self._clock.today()
        first = today.replace(day=1)
        next_month = (first + timedelta(days=32)).replace(day=1)
        return self.summary(first, next_month - timedelta(days=1))

    def clashes(self, shift: Shift, agenda_items: list[AgendaItem]) -> list[AgendaItem]:
        """Items (classes, events, other shifts) that overlap the given shift."""
        return [i for i in agenda_items
                if not (i.kind is ItemKind.SHIFT and i.ref_id == shift.id)
                and shift.overlaps(i.day, i.time)]


def shift_agenda_items(items: list[ShiftItem]) -> list[AgendaItem]:
    """One AgendaItem per calendar day each shift touches."""
    result = []
    for item in items:
        job = item.job
        for day, time in item.shift.segments():
            result.append(AgendaItem(ItemKind.SHIFT, item.shift.id, day, time,
                                     job.name if job else "Shift",
                                     job.color if job else "#0090ff",
                                     details=item.shift.notes))
    return result
