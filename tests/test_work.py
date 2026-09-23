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
