from datetime import date

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
