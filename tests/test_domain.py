from datetime import date, timedelta

import pytest

from quire.domain import (
    ClassSlot, Course, DueBucket, Event, Task, TimeRange, ValidationError, derive_note_title,
)

TODAY = date(2026, 9, 23)  # Wednesday


def test_time_range_rejects_backwards_and_out_of_day():
    with pytest.raises(ValidationError):
        TimeRange(600, 600)
    with pytest.raises(ValidationError):
        TimeRange(600, 540)
    with pytest.raises(ValidationError):
        TimeRange(-1, 60)
    assert TimeRange(0, 24 * 60).duration == 24 * 60


def test_class_slot_weekday_bounds():
    with pytest.raises(ValidationError):
        ClassSlot(7, TimeRange(540, 600))


def test_course_requires_name():
    with pytest.raises(ValidationError):
        Course("   ").validate()


def test_course_next_meeting_wraps_around_week():
    course = Course("Maths", slots=[ClassSlot(0, TimeRange(540, 600)),
                                    ClassSlot(2, TimeRange(540, 600))])
    assert course.next_meeting_after(TODAY) == date(2026, 9, 28)  # next Monday
    assert course.next_meeting_after(date(2026, 9, 21)) == TODAY
    assert Course("Empty").next_meeting_after(TODAY) is None


def test_course_room_falls_back_to_default():
    course = Course("Chem", room="Lab 1")
    assert course.room_for(ClassSlot(0, TimeRange(540, 600))) == "Lab 1"
    assert course.room_for(ClassSlot(0, TimeRange(540, 600), "Lab 3")) == "Lab 3"


def test_event_requires_title():
    with pytest.raises(ValidationError):
        Event(TODAY, TimeRange(540, 600), "").validate()


def test_sleep_log_crosses_midnight_and_checks_its_limits():
    from quire.domain import SleepLog, bedtime_for, sleep_stats
    night = SleepLog(TODAY, 23 * 60 + 30, 6 * 60 + 15, 4)
    night.validate()
    assert night.minutes == 6 * 60 + 45
    assert night.fell_asleep_on == TODAY - timedelta(days=1)
    assert SleepLog(TODAY, 1 * 60, 7 * 60).fell_asleep_on == TODAY  # fell asleep after midnight
    for bad in (SleepLog(TODAY, 600, 610), SleepLog(TODAY, 0, 1100), SleepLog(TODAY, 600, 1400, 9)):
        with pytest.raises(ValidationError):
            bad.validate()
    assert bedtime_for(6 * 60, 8) == 22 * 60 and bedtime_for(1 * 60, 8) == 17 * 60

    stats = sleep_stats([SleepLog(TODAY, 23 * 60, 7 * 60, 4), SleepLog(TODAY, 1 * 60, 7 * 60, 2)], 8)
    assert stats.nights == 2 and stats.average_minutes == 7 * 60
    assert stats.average_bedtime == 0  # midway between 23:00 and 01:00
    assert stats.enough == 1 and stats.shortfall_minutes == 120 and stats.average_quality == 3
    assert sleep_stats([], 8).nights == 0


def test_milestone_has_no_duration_beyond_the_minimum():
    from quire.domain import milestone_time
    assert Event(TODAY, milestone_time(360), "Wake up").is_milestone
    assert not Event(TODAY, TimeRange(360, 420), "Run").is_milestone
    assert milestone_time(24 * 60).end == 24 * 60  # clamped into the day


@pytest.mark.parametrize("due, done, bucket", [
    (date(2026, 9, 20), False, DueBucket.OVERDUE),
    (TODAY, False, DueBucket.TODAY),
    (date(2026, 9, 30), False, DueBucket.UPCOMING),
    (date(2026, 10, 1), False, DueBucket.LATER),
    (None, False, DueBucket.UNDATED),
    (date(2026, 9, 20), True, DueBucket.DONE),
])
def test_task_buckets(due, done, bucket):
    assert Task("x", due=due, done=done).bucket(TODAY) is bucket


def test_done_task_is_never_overdue():
    assert not Task("x", due=date(2026, 1, 1), done=True).is_overdue(TODAY)


@pytest.mark.parametrize("body, title", [
    ("# Heading\nbody", "Heading"),
    ("\n\n  ## Spaced  \n", "Spaced"),
    ("", "Untitled"),
    ("###", "Untitled"),
])
def test_note_title(body, title):
    assert derive_note_title(body) == title


def test_topic_normalisation():
    from quire.domain import normalize_topic
    assert normalize_topic("  Cell   respiration ") == "Cell respiration"
    assert normalize_topic("x" * 100) == "x" * 60


def test_shift_rules():
    from quire.domain import Shift

    evening = Shift.between(1, TODAY, 17 * 60, 22 * 60, break_minutes=30)
    assert (evening.duration, evening.paid_minutes, evening.ends_next_day) == (300, 270, False)
    assert evening.pay(9.0) == 40.5 and evening.pay(None) is None

    late = Shift.between(1, TODAY, 18 * 60, 1 * 60)
    assert late.ends_next_day and late.duration == 7 * 60
    assert [(d.day, t.start, t.end) for d, t in late.segments()] == [(23, 1080, 1440), (24, 0, 60)]
    assert late.overlaps(date(2026, 9, 24), TimeRange(30, 90))
    assert not late.overlaps(TODAY, TimeRange(600, 700))

    for bad in (Shift(1, TODAY, 600, 0), Shift(1, TODAY, 600, 17 * 60),
                Shift(1, TODAY, 600, 60, break_minutes=60), Shift(1, TODAY, 1440, 60)):
        with pytest.raises(ValidationError):
            bad.validate()


def test_job_rules():
    from quire.domain import Job
    with pytest.raises(ValidationError):
        Job(" ").validate()
    with pytest.raises(ValidationError):
        Job("Café", hourly_rate=-1).validate()
