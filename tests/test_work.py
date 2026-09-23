from datetime import date, timedelta

import pytest

from quire.application.bus import Topic
from quire.application.dto import ItemKind
from quire.domain import ClassSlot, Course, Event, Job, Shift, TimeRange, ValidationError

from .conftest import TODAY  # Wednesday 23 Sep 2026; the fixed clock says 12:00

MONDAY = TODAY - timedelta(days=2)


def job(services, name="Pizzeria", rate=8.5, color="#f76b15"):
    return services.work.save_job(Job(name, color, rate))


def test_repeat_creates_weekly_copies(services):
    pizzeria = job(services)
    ids = services.work.save_shift(Shift.between(pizzeria, TODAY, 18 * 60, 22 * 60),
                                   repeat_weeks=3)
    assert len(ids) == 4
    days = [i.shift.day for i in services.work.shifts_between(TODAY, TODAY + timedelta(weeks=4))]
    assert days == [TODAY + timedelta(weeks=n) for n in range(4)]


def test_shift_needs_an_existing_job_and_edits_cannot_repeat(services):
    with pytest.raises(ValidationError):
        services.work.save_shift(Shift.between(999, TODAY, 600, 660))
    pizzeria = job(services)
    (shift_id,) = services.work.save_shift(Shift.between(pizzeria, TODAY, 600, 660))
    shift = services.work.shift(shift_id)
    with pytest.raises(ValidationError):
        services.work.save_shift(shift, repeat_weeks=2)


def test_week_summary_counts_paid_hours_and_pay_per_job(services):
    pizzeria = job(services, "Pizzeria", 8.5)
    babysit = job(services, "Babysitting", None)
    services.work.save_shift(Shift.between(pizzeria, MONDAY, 18 * 60, 22 * 60, break_minutes=30))
    services.work.save_shift(Shift.between(pizzeria, TODAY, 18 * 60, 1 * 60))
    services.work.save_shift(Shift.between(babysit, TODAY + timedelta(days=2), 15 * 60, 18 * 60))
    services.work.save_shift(Shift.between(pizzeria, MONDAY + timedelta(days=7), 18 * 60, 22 * 60))

    week = services.work.week_summary()
    assert week.shifts == 3
    assert week.minutes == 210 + 420 + 180
    by_job = {t.job.name: t for t in week.per_job}
    assert by_job["Pizzeria"].pay == round(10.5 * 8.5, 2)
    assert by_job["Babysitting"].pay is None
    assert week.pay == round(10.5 * 8.5, 2)  # only jobs with a rate are summed


def test_month_summary_covers_the_calendar_month(services):
    pizzeria = job(services)
    services.work.save_shift(Shift.between(pizzeria, date(2026, 9, 1), 600, 660))
    services.work.save_shift(Shift.between(pizzeria, date(2026, 9, 30), 600, 660))
    services.work.save_shift(Shift.between(pizzeria, date(2026, 10, 1), 600, 660))
    assert services.work.month_summary().shifts == 2


def test_upcoming_skips_finished_shifts(services):
    pizzeria = job(services)
    services.work.save_shift(Shift.between(pizzeria, TODAY, 8 * 60, 11 * 60))  # ended at 11
    services.work.save_shift(Shift.between(pizzeria, TODAY, 11 * 60, 14 * 60))  # running now
    services.work.save_shift(Shift.between(pizzeria, TODAY - timedelta(days=1), 22 * 60, 13 * 60))
    services.work.save_shift(Shift.between(pizzeria, TODAY + timedelta(days=1), 600, 660))
    starts = [(i.shift.day, i.shift.start) for i in services.work.upcoming()]
    assert starts == [(TODAY - timedelta(days=1), 22 * 60), (TODAY, 11 * 60),
                      (TODAY + timedelta(days=1), 600)]


def test_overnight_shift_shows_on_both_days(services):
    pizzeria = job(services)
    services.work.save_shift(Shift.between(pizzeria, TODAY, 20 * 60, 2 * 60))
    today = [i for i in services.planner.day_agenda(TODAY).items if i.kind is ItemKind.SHIFT]
    tomorrow = [i for i in services.planner.day_agenda(TODAY + timedelta(days=1)).items
                if i.kind is ItemKind.SHIFT]
    assert [(i.title, i.time.start, i.time.end) for i in today] == [("Pizzeria", 1200, 1440)]
    assert [(i.time.start, i.time.end) for i in tomorrow] == [(0, 120)]
    assert services.planner.day_agenda(TODAY).shift_count == 1


def test_weekend_shift_widens_the_week(services):
    pizzeria = job(services)
    assert len(services.planner.week_agenda(TODAY).days) == 5
    services.work.save_shift(Shift.between(pizzeria, date(2026, 9, 26), 600, 900))
    week = services.planner.week_agenda(TODAY)
    assert len(week.days) == 7
    assert any(i.kind is ItemKind.SHIFT for i in week.items)


def test_clashes_with_classes_events_and_other_shifts(services):
    pizzeria = job(services)
    services.timetable.save_course(Course("Maths", slots=[ClassSlot(2, TimeRange(600, 660))]))
    services.planner.save_event(Event(TODAY, TimeRange(700, 760), "Dentist"))
    (other,) = services.work.save_shift(Shift.between(pizzeria, TODAY, 750, 800))

    new = Shift.between(pizzeria, TODAY, 630, 760)
    items = services.planner.items_between(TODAY, TODAY + timedelta(days=1))
    assert sorted(i.title for i in services.work.clashes(new, items)) == [
        "Dentist", "Maths", "Pizzeria"]
    # A saved shift doesn't clash with itself (only with the dentist it overlaps).
    saved = services.work.shift(other)
    assert [i.title for i in services.work.clashes(saved, items)] == ["Dentist"]


def test_deleting_a_job_deletes_its_shifts(services):
    pizzeria = job(services)
    services.work.save_shift(Shift.between(pizzeria, TODAY, 600, 660), repeat_weeks=2)
    services.work.delete_job(pizzeria)
    assert services.work.shifts_between(TODAY, TODAY + timedelta(weeks=3)) == []


def test_work_changes_are_published(services):
    seen = []
    services.bus.subscribe(seen.append)
    pizzeria = job(services)
    services.work.save_shift(Shift.between(pizzeria, TODAY, 600, 660))
    assert seen == [Topic.WORK, Topic.WORK]


# ---- weekly schedule ------------------------------------------------------------

from quire.domain import ShiftPattern, reschedule  # noqa: E402

TUESDAY_EVENINGS = ShiftPattern.between(1, 18 * 60, 22 * 60, 30)
SATURDAY_LATE = ShiftPattern.between(5, 19 * 60, 1 * 60, 30)


def scheduled_job(services, *patterns, rate=10.0):
    return services.work.save_job(Job("Pizzeria", "#f76b15", rate), weekly=list(patterns))


def test_weekly_shifts_show_every_week_from_this_week(services):
    job_id = scheduled_job(services, TUESDAY_EVENINGS)
    items = services.work.shifts_between(MONDAY - timedelta(weeks=1), MONDAY + timedelta(weeks=3))
    assert [i.shift.day for i in items] == [MONDAY + timedelta(days=1, weeks=n) for n in range(3)]
    assert all(i.shift.recurring and i.shift.job_id == job_id for i in items)

    week = services.planner.week_agenda(TODAY)
    weekly = [i for i in week.items if i.kind is ItemKind.WEEKLY_SHIFT]
    assert [(i.day.weekday(), i.time.start) for i in weekly] == [(1, 18 * 60)]


def test_weekly_shifts_count_towards_hours_and_pay(services):
    scheduled_job(services, TUESDAY_EVENINGS, SATURDAY_LATE, rate=10.0)
    week = services.work.week_summary()
    assert week.shifts == 2
    assert week.minutes == 210 + 330
    assert week.pay == round((210 + 330) / 60 * 10, 2)


def test_changing_the_schedule_keeps_past_weeks(services, clock):
    job_id = scheduled_job(services, TUESDAY_EVENINGS)
    # Pretend the schedule was set up weeks ago.
    job = services.work.job(job_id)
    job.schedule[0].since = MONDAY - timedelta(weeks=4)
    services.work._jobs.update(job)

    wednesday = ShiftPattern.between(2, 17 * 60, 21 * 60)
    services.work.save_job(services.work.job(job_id), weekly=[wednesday])

    past = services.work.shifts_between(MONDAY - timedelta(weeks=2), MONDAY - timedelta(days=1))
    assert {i.shift.day.weekday() for i in past} == {1}  # history still says Tuesdays
    now = services.work.shifts_between(MONDAY, MONDAY + timedelta(days=6))
    assert [i.shift.day.weekday() for i in now] == [2]
    assert [p.weekday for p in services.work.job(job_id).active_schedule(TODAY)] == [2]


def test_saving_a_job_without_a_schedule_keeps_it(services):
    job_id = scheduled_job(services, TUESDAY_EVENINGS)
    job = services.work.job(job_id)
    job.hourly_rate = 12.0
    services.work.save_job(Job(job.name, job.color, 12.0, job.id))  # e.g. a rename/rate edit
    assert len(services.work.job(job_id).active_schedule(TODAY)) == 1


def test_reschedule_drops_patterns_created_this_week():
    fresh = ShiftPattern.between(1, 600, 660, since=MONDAY)
    assert reschedule([fresh], [], MONDAY) == []


def test_skip_and_replace_one_week(services):
    job_id = scheduled_job(services, TUESDAY_EVENINGS)
    tuesday = MONDAY + timedelta(days=1)
    next_tuesday = tuesday + timedelta(weeks=1)

    services.work.skip_occurrence(job_id, tuesday, 18 * 60)
    services.work.save_shift(Shift.between(job_id, next_tuesday, 16 * 60, 20 * 60),
                             replaces=(job_id, next_tuesday, 18 * 60))

    items = services.work.shifts_between(MONDAY, MONDAY + timedelta(weeks=3))
    assert [(i.shift.day, i.shift.start, i.shift.recurring) for i in items] == [
        (next_tuesday, 16 * 60, False),
        (tuesday + timedelta(weeks=2), 18 * 60, True),
    ]


def test_replacement_does_not_clash_with_the_occurrence_it_replaces(services):
    job_id = scheduled_job(services, TUESDAY_EVENINGS)
    tuesday = MONDAY + timedelta(days=1)
    moved = Shift.between(job_id, tuesday, 17 * 60, 21 * 60)
    items = services.planner.items_between(tuesday, tuesday + timedelta(days=1))
    assert [i.title for i in services.work.clashes(moved, items)] == ["Pizzeria"]
    assert services.work.clashes(moved, items, replaces=(job_id, tuesday, 18 * 60)) == []


def test_overnight_weekly_shift_spans_saturday_and_sunday(services):
    scheduled_job(services, SATURDAY_LATE)
    saturday, sunday = MONDAY + timedelta(days=5), MONDAY + timedelta(days=6)
    sat = [i for i in services.planner.day_agenda(saturday).items if i.kind is ItemKind.WEEKLY_SHIFT]
    sun = [i for i in services.planner.day_agenda(sunday).items if i.kind is ItemKind.WEEKLY_SHIFT]
    assert [(i.time.start, i.time.end, i.origin) for i in sat] == [(1140, 1440, (saturday, 1140))]
    assert [(i.time.start, i.time.end, i.origin) for i in sun] == [(0, 60, (saturday, 1140))]


def test_invalid_pattern_is_rejected(services):
    with pytest.raises(ValidationError):
        services.work.save_job(Job("x"), weekly=[ShiftPattern(1, 600, 60, break_minutes=60)])



def test_repeat_every_work_day(services):
    from quire.domain import WORK_DAYS
    job_id = services.work.save_job(Job("Café", "#f76b15", 9.0))
    added = services.work.add_weekly(job_id, WORK_DAYS, 7 * 60, 9 * 60, since=TODAY)
    assert added == 5
    items = services.work.shifts_between(MONDAY, MONDAY + timedelta(days=13))
    days = [i.shift.day for i in items]
    # From today (Wednesday) on, Monday to Friday only.
    assert days[0] == TODAY and all(d.weekday() < 5 for d in days)
    assert len(days) == 3 + 5
    # Adding the same again doesn't double up.
    assert services.work.add_weekly(job_id, WORK_DAYS, 7 * 60, 9 * 60, since=TODAY) == 0


def test_repeat_until_a_date(services):
    job_id = services.work.save_job(Job("Summer camp"))
    last_day = TODAY + timedelta(days=9)
    services.work.add_weekly(job_id, [0, 2, 4], 9 * 60, 13 * 60, since=TODAY, until=last_day)
    items = services.work.shifts_between(TODAY, TODAY + timedelta(weeks=4))
    assert max(i.shift.day for i in items) <= last_day
    assert len(items) == 5  # Wed, Fri, Mon, Wed, Fri
    with pytest.raises(ValidationError):
        services.work.add_weekly(job_id, [], 600, 660)
    with pytest.raises(ValidationError):
        services.work.add_weekly(job_id, [1], 600, 660, since=TODAY, until=TODAY - timedelta(days=1))


def test_ending_repeat_is_kept_when_editing_the_schedule(services):
    job_id = services.work.save_job(Job("Summer camp"))
    services.work.add_weekly(job_id, [2], 9 * 60, 13 * 60, since=TODAY,
                             until=TODAY + timedelta(weeks=2))
    job = services.work.job(job_id)
    wanted = [ShiftPattern(p.weekday, p.start, p.duration, p.break_minutes)
              for p in job.active_schedule(TODAY)]
    services.work.save_job(job, weekly=wanted)  # re-saving the editor unchanged
    (pattern,) = services.work.job(job_id).active_schedule(TODAY)
    assert pattern.until == TODAY + timedelta(weeks=2)



def test_net_pay_after_tax_and_deductions(services):
    from quire.domain import net_pay
    assert net_pay(100.0, 20) == 80.0 and net_pay(None, 20) is None and net_pay(50.0, 0) == 50.0

    occasional = services.work.save_job(Job("Tutoring", hourly_rate=15.0, deductions=20.0))
    employee = services.work.save_job(Job("Pizzeria", hourly_rate=10.0, deductions=9.19))
    services.work.save_shift(Shift.between(occasional, TODAY, 16 * 60, 18 * 60))   # 30 gross
    services.work.save_shift(Shift.between(employee, TODAY, 18 * 60, 22 * 60))     # 40 gross

    week = services.work.week_summary()
    assert week.pay == 70.0
    assert week.net == round(24.0 + 40 * (1 - 0.0919), 2)
    by_job = {t.job.name: t for t in week.per_job}
    assert (by_job["Tutoring"].pay, by_job["Tutoring"].net) == (30.0, 24.0)
    assert services.work.job(occasional).deductions == 20.0


def test_deductions_must_be_a_percentage(services):
    for bad in (-1, 100, 150):
        with pytest.raises(ValidationError):
            services.work.save_job(Job("x", deductions=bad))
