from __future__ import annotations

from datetime import date, timedelta

from ...domain import (
    Job, NotFound, Payslip, Shift, ShiftPattern, TimeRange, ValidationError, monthly_gross,
    monthly_share, reschedule, take_home, work_shifts, year_payslips,
)
from ..bus import ChangeBus, Topic
from ..dto import AgendaItem, ItemKind, JobTotal, ShiftItem, ShiftPreview, WorkSummary
from ..inputs import JobInput, PatternInput, ShiftInput
from ..ports import Clock, JobRepository, ShiftRepository
from ..records import (
    JobRecord, PayslipRecord, ShiftRecord, job_record, payslip_record, shift_record, span,
)

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
        job.pay_mode, job.monthly_pay, job.mensilities = (data.pay_mode, data.monthly_pay,
                                                         data.mensilities)
        job.contract_start, job.contract_end = data.contract_start, data.contract_end
        job.tax_model, job.inps, job.addizionali = data.tax_model, data.inps, data.addizionali
        job.fixed_term, job.cuneo = data.fixed_term, data.cuneo
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
        gross = self._shift_pay(job, shift)
        return ShiftPreview(shift.duration, shift.paid_minutes, shift.ends_next_day, gross,
                            self._shift_net(job, shift, gross, {}))

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

    # ---- pay ----------------------------------------------------------------------

    @staticmethod
    def _shift_pay(job: Job | None, shift: Shift) -> float | None:
        """Gross pay of one shift: only hourly jobs pay by the shift."""
        if job is None or job.pay_mode != "hourly":
            return None
        return shift.pay(job.hourly_rate)

    def _slips(self, job: Job, year: int, cache: dict) -> list[Payslip]:
        """The year's twelve payslips of a job (worked out once per request)."""
        key = (job.id, year)
        if key not in cache:
            first, last = date(year, 1, 1), date(year, 12, 31)
            terms = job.terms
            if terms.pay_mode == "monthly":
                grosses, worked = [monthly_gross(terms, year, m) for m in range(1, 13)], None
            else:
                shifts = [s for s in work_shifts([job], self._shifts.starting_between(first, last),
                                                 self._shifts.skipped(first, last), first, last)
                          if s.job_id == job.id and s.day.year == year]
                totals = [0.0] * 12
                for s in shifts:
                    totals[s.day.month - 1] += s.pay(job.hourly_rate) or 0.0
                grosses = [(round(t, 2), 0.0) for t in totals]
                worked = [s.day for s in shifts]
            cache[key] = year_payslips(terms, year, grosses, worked)
        return cache[key]

    def _shift_net(self, job: Job | None, shift: Shift, gross: float | None,
                   cache: dict) -> float | None:
        if gross is None or job is None:
            return gross
        return take_home(job.terms, self._slips(job, shift.day.year, cache)[shift.day.month - 1],
                         gross)

    def payslips(self, job_id: int, year: int) -> list[PayslipRecord]:
        """The months of `year` in which the job pays something."""
        job = self._job(job_id)
        return [payslip_record(p) for p in self._slips(job, year, {}) if p.gross > 0]

    def shifts_between(self, first: date, last: date) -> list[ShiftItem]:
        """One-off shifts and weekly-schedule occurrences starting on first..last."""
        jobs = self._jobs.list()
        today = self._clock.today()
        by_id = {j.id: j for j in jobs}
        records = {j.id: job_record(j, today) for j in jobs}
        shifts = work_shifts(jobs, self._shifts.starting_between(first, last),
                             self._shifts.skipped(first, last), first, last)
        items, cache = [], {}
        for s in shifts:
            job = by_id.get(s.job_id)
            gross = self._shift_pay(job, s)
            items.append(ShiftItem(shift_record(s), records.get(s.job_id), gross,
                                   self._shift_net(job, s, gross, cache)))
        return items

    def upcoming(self, days: int = 28) -> list[ShiftItem]:
        """Shifts that haven't ended yet, soonest first."""
        now = self._clock.now()
        today = now.date()
        minute = now.hour * 60 + now.minute
        return [item for item in self.shifts_between(today - timedelta(days=1),
                                                     today + timedelta(days=days))
                if (item.shift.day - today).days * 1440 + item.shift.end > minute]

    def _pay_between(self, job: Job, items: list[ShiftItem], first: date, last: date,
                     cache: dict) -> tuple[float | None, float | None]:
        """Gross and take-home pay of a job over first..last."""
        terms = job.terms
        if terms.pay_mode == "monthly":
            if terms.monthly_pay is None:
                return None, None
            gross = net = 0.0
            year, month = first.year, first.month
            while (year, month) <= (last.year, last.month):
                g, n = monthly_share(terms, self._slips(job, year, cache)[month - 1], first, last)
                gross, net = gross + g, net + n
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            return round(gross, 2), round(net, 2)
        if any(i.pay is None for i in items):
            return None, None
        by_month: dict[tuple[int, int], float] = {}
        for i in items:
            key = (i.shift.day.year, i.shift.day.month)
            by_month[key] = by_month.get(key, 0.0) + i.pay
        net = sum(take_home(terms, self._slips(job, y, cache)[m - 1], g)
                  for (y, m), g in by_month.items())
        return round(sum(by_month.values()), 2), round(net, 2)

    def summary(self, first: date, last: date) -> WorkSummary:
        """Paid hours and estimated pay for shifts starting in [first, last]."""
        items = self.shifts_between(first, last)
        jobs = {j.id: j for j in self._jobs.list()}
        per_job: dict[int, list[ShiftItem]] = {}
        for item in items:
            per_job.setdefault(item.shift.job_id, []).append(item)
        for job in jobs.values():  # a monthly job is paid even in a week without shifts
            if job.pay_mode == "monthly" and job.monthly_pay is not None:
                per_job.setdefault(job.id, [])
        cache, totals = {}, []
        for job_id, job_items in per_job.items():
            job = jobs.get(job_id)
            gross, net = self._pay_between(job, job_items, first, last, cache) if job else (
                None, None)
            totals.append(JobTotal(job_items[0].job if job_items else job_record(
                job, self._clock.today()), sum(i.shift.paid_minutes for i in job_items),
                gross, net))
        totals = [t for t in totals if t.minutes or t.pay]
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
