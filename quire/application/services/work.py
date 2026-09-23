from __future__ import annotations

from datetime import date, timedelta

from ...domain import (
    Job, NotFound, Shift, ShiftPattern, ValidationError, reschedule, work_shifts,
)
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

    def _this_monday(self) -> date:
        today = self._clock.today()
        return today - timedelta(days=today.weekday())

    def save_job(self, job: Job, weekly: list[ShiftPattern] | None = None) -> int:
        """Save a job; `weekly` replaces its weekly schedule from this week on.

        Leaving `weekly` out keeps the stored schedule untouched.
        """
        job.name = job.name.strip()
        stored = self._jobs.get(job.id) if job.id is not None else None
        current = stored.schedule if stored else []
        job.schedule = (current if weekly is None
                        else reschedule(current, weekly, self._this_monday()))
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

    def save_shift(self, shift: Shift, repeat_weeks: int = 0,
                   replaces: tuple[int, date, int] | None = None) -> list[int]:
        """Save a shift; for a new one, optionally copy it to the following weeks.

        `replaces` names a weekly-schedule occurrence (job id, day, start) that this
        shift stands in for, e.g. a different time just this week.
        """
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
        if replaces is not None:
            self._shifts.skip(*replaces)
        self._bus.publish(Topic.WORK)
        return ids

    def add_weekly(self, job_id: int, weekdays, start: int, end: int, break_minutes: int = 0,
                   since: date | None = None, until: date | None = None) -> int:
        """Make a shift repeat on the given weekdays (e.g. every work day) from `since`.

        Returns how many weekly patterns were added; days already scheduled at the same
        time are left alone.
        """
        job = self.job(job_id)
        weekdays = sorted(set(weekdays))
        if not weekdays:
            raise ValidationError("Pick at least one day for the shift to repeat on.")
        since = since or self._clock.today()
        today = self._clock.today()
        taken = {p.key for p in job.active_schedule(today)}
        added = 0
        for weekday in weekdays:
            pattern = ShiftPattern.between(weekday, start, end, break_minutes,
                                           since=since, until=until)
            pattern.validate()
            if pattern.key not in taken:
                job.schedule.append(pattern)
                taken.add(pattern.key)
                added += 1
        self._jobs.update(job)
        self._bus.publish(Topic.WORK)
        return added

    def skip_occurrence(self, job_id: int, day: date, start: int):
        """Take one week's occurrence of a weekly shift off the schedule."""
        self._shifts.skip(job_id, day, start)
        self._bus.publish(Topic.WORK)

    def delete_shift(self, shift_id: int):
        self._shifts.delete(shift_id)
        self._bus.publish(Topic.WORK)

    def shifts_between(self, first: date, last: date) -> list[ShiftItem]:
        """One-off shifts and weekly-schedule occurrences starting on first..last."""
        jobs = self._jobs.list()
        by_id = {j.id: j for j in jobs}
        shifts = work_shifts(jobs, self._shifts.starting_between(first, last),
                             self._shifts.skipped(first, last), first, last)
        return [ShiftItem(s, by_id.get(s.job_id)) for s in shifts]

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
            nets = [i.net for i in job_items]
            unknown = any(p is None for p in pays)
            totals.append(JobTotal(
                job_items[0].job, sum(i.shift.paid_minutes for i in job_items),
                None if unknown else round(sum(pays), 2),
                None if unknown else round(sum(nets), 2)))
        totals.sort(key=lambda t: t.job.name.casefold() if t.job else "")
        gross = [t.pay for t in totals if t.pay is not None]
        net = [t.net for t in totals if t.net is not None]
        return WorkSummary(first, last, sum(t.minutes for t in totals),
                           round(sum(gross), 2) if gross else None, len(items), tuple(totals),
                           round(sum(net), 2) if net else None)

    def week_summary(self) -> WorkSummary:
        today = self._clock.today()
        monday = today - timedelta(days=today.weekday())
        return self.summary(monday, monday + timedelta(days=6))

    def month_summary(self) -> WorkSummary:
        today = self._clock.today()
        first = today.replace(day=1)
        next_month = (first + timedelta(days=32)).replace(day=1)
        return self.summary(first, next_month - timedelta(days=1))

    def clashes(self, shift: Shift, agenda_items: list[AgendaItem],
                replaces: tuple[int, date, int] | None = None) -> list[AgendaItem]:
        """Items (classes, events, other shifts) that overlap the given shift.

        The shift itself, and the weekly occurrence it `replaces`, don't count.
        """
        def is_self(i: AgendaItem) -> bool:
            if i.kind is ItemKind.SHIFT:
                return shift.id is not None and i.ref_id == shift.id
            if i.kind is ItemKind.WEEKLY_SHIFT and replaces is not None:
                return (i.ref_id, *i.origin) == replaces
            return False

        return [i for i in agenda_items if not is_self(i) and shift.overlaps(i.day, i.time)]


def shift_agenda_items(items: list[ShiftItem]) -> list[AgendaItem]:
    """One AgendaItem per calendar day each shift touches."""
    result = []
    for item in items:
        shift, job = item.shift, item.job
        kind = ItemKind.WEEKLY_SHIFT if shift.recurring else ItemKind.SHIFT
        ref = shift.job_id if shift.recurring else shift.id
        for day, time in shift.segments():
            result.append(AgendaItem(kind, ref, day, time, job.name if job else "Shift",
                                     job.color if job else "#0090ff", details=shift.notes,
                                     origin=(shift.day, shift.start)))
    return result
