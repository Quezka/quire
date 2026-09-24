from __future__ import annotations

from datetime import date, timedelta

from ...domain import (
    Job, NotFound, Shift, ShiftPattern, TimeRange, ValidationError, net_pay, reschedule,
    work_shifts,
)
from ..bus import ChangeBus, Topic
from ..dto import AgendaItem, ItemKind, JobTotal, ShiftItem, ShiftPreview, WorkSummary
from ..inputs import JobInput, PatternInput, ShiftInput
from ..ports import Clock, JobRepository, ShiftRepository
from ..records import JobRecord, ShiftRecord, job_record, shift_record, span

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

    def jobs(self) -> list[JobRecord]:
        today = self._clock.today()
        return [job_record(j, today) for j in self._jobs.list()]

    def _job(self, job_id: int) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"Job {job_id} does not exist.")
        return job

    def job(self, job_id: int) -> JobRecord:
        return job_record(self._job(job_id), self._clock.today())

    def _this_monday(self) -> date:
        today = self._clock.today()
        return today - timedelta(days=today.weekday())

    def save_job(self, job_id: int | None, data: JobInput,
                 weekly: list[PatternInput] | None = None) -> int:
        """Create or change a job; `weekly` replaces its weekly schedule from this week on.

        Leaving `weekly` out keeps the stored schedule untouched.
        """
        job = Job(data.name) if job_id is None else self._job(job_id)
        job.name, job.color = data.name.strip(), data.color
        job.hourly_rate, job.deductions = data.hourly_rate, data.deductions
        if weekly is not None:
            wanted = [ShiftPattern.between(p.weekday, p.start, p.end, p.break_minutes)
                      for p in weekly]
            job.schedule = reschedule(job.schedule, wanted, self._this_monday())
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

    def _shift(self, shift_id: int) -> Shift:
        shift = self._shifts.get(shift_id)
        if shift is None:
            raise NotFound(f"Shift {shift_id} does not exist.")
        return shift

    def shift(self, shift_id: int) -> ShiftRecord:
        return shift_record(self._shift(shift_id))

    @staticmethod
    def _from_input(data: ShiftInput, shift_id: int | None = None) -> Shift:
        return Shift.between(data.job_id, data.day, data.start, data.end,
                             break_minutes=data.break_minutes, notes=data.notes, id=shift_id)

    def preview(self, data: ShiftInput) -> ShiftPreview:
        """Paid time and pay of a shift being edited (nothing is saved or validated)."""
        shift = self._from_input(data)
        job = self._jobs.get(data.job_id)
        gross = shift.pay(job.hourly_rate if job else None)
        return ShiftPreview(shift.duration, shift.paid_minutes, shift.ends_next_day, gross,
                            net_pay(gross, job.deductions if job else 0.0))

    def save_shift(self, shift_id: int | None, data: ShiftInput, repeat_weeks: int = 0,
                   replaces: tuple[int, date, int] | None = None) -> list[int]:
        """Save a shift; for a new one, optionally copy it to the following weeks.

        `replaces` names a weekly-schedule occurrence (job id, day, start) that this
        shift stands in for, e.g. a different time just this week.
        """
        if shift_id is not None:
            self._shift(shift_id)  # must exist
        shift = self._from_input(data, shift_id)
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
        job = self._job(job_id)
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
        today = self._clock.today()
        by_id = {j.id: j for j in jobs}
        records = {j.id: job_record(j, today) for j in jobs}
        shifts = work_shifts(jobs, self._shifts.starting_between(first, last),
                             self._shifts.skipped(first, last), first, last)
        items = []
        for s in shifts:
            job = by_id.get(s.job_id)
            gross = s.pay(job.hourly_rate if job else None)
            items.append(ShiftItem(shift_record(s), records.get(s.job_id), gross,
                                   net_pay(gross, job.deductions if job else 0.0)))
        return items

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

    def clashes(self, shift_id: int | None, data: ShiftInput, agenda_items: list[AgendaItem],
                replaces: tuple[int, date, int] | None = None) -> list[AgendaItem]:
        """Items (classes, events, other shifts) that overlap a shift being edited.

        The shift itself, and the weekly occurrence it `replaces`, don't count.
        """
        shift = self._from_input(data, shift_id)
        def is_self(i: AgendaItem) -> bool:
            if i.kind is ItemKind.SHIFT:
                return shift.id is not None and i.ref_id == shift.id
            if i.kind is ItemKind.WEEKLY_SHIFT and replaces is not None:
                return (i.ref_id, *i.origin) == replaces
            return False

        return [i for i in agenda_items
                if not is_self(i) and shift.overlaps(i.day, TimeRange(i.time.start, i.time.end))]


def shift_agenda_items(pairs: list[tuple[Shift, Job | None]]) -> list[AgendaItem]:
    """One AgendaItem per calendar day each shift touches."""
    result = []
    for shift, job in pairs:
        kind = ItemKind.WEEKLY_SHIFT if shift.recurring else ItemKind.SHIFT
        ref = shift.job_id if shift.recurring else shift.id
        for day, time in shift.segments():
            result.append(AgendaItem(kind, ref, day, span(time), job.name if job else "Shift",
                                     job.color if job else "#0090ff", details=shift.notes,
                                     origin=(shift.day, shift.start)))
    return result
