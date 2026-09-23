from datetime import date, timedelta

import pytest

from quire.application.bus import Topic
from quire.application.dto import ItemKind
from quire.domain import (
    ClassSlot, Course, DueBucket, Event, NotFound, Task, TaskKind, TimeRange, ValidationError,
)

from .conftest import TODAY

YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


def add_course(services, name="Maths", slots=((2, 540, 600),), color="#4f7cff"):
    course = Course(name, color=color,
                    slots=[ClassSlot(wd, TimeRange(s, e)) for wd, s, e in slots])
    return services.timetable.save_course(course)


def test_course_round_trip_keeps_slots(services):
    course_id = add_course(services, slots=((0, 540, 600), (2, 600, 660)))
    course = services.timetable.course(course_id)
    assert [(s.weekday, s.time.start) for s in course.slots] == [(0, 540), (2, 600)]

    course.slots = course.slots[:1]
    services.timetable.save_course(course)
    assert len(services.timetable.course(course_id).slots) == 1


def test_invalid_course_is_not_stored(services):
    with pytest.raises(ValidationError):
        services.timetable.save_course(Course(""))
    assert services.timetable.courses() == []


def test_missing_entities_raise_not_found(services):
    with pytest.raises(NotFound):
        services.timetable.course(99)
    with pytest.raises(NotFound):
        services.tasks.task(99)


def test_day_agenda_merges_classes_and_events_in_time_order(services):
    add_course(services, "Maths", ((2, 600, 660),))
    services.planner.save_event(Event(TODAY, TimeRange(480, 510), "Breakfast"))
    services.planner.save_event(Event(TOMORROW, TimeRange(480, 510), "Not today"))

    agenda = services.planner.day_agenda(TODAY)
    assert [(i.kind, i.title) for i in agenda.items] == [
        (ItemKind.EVENT, "Breakfast"), (ItemKind.CLASS, "Maths")]
    assert agenda.is_today and agenda.has_courses


def test_overdue_tasks_only_follow_you_to_today(services):
    services.tasks.save(Task("late", due=YESTERDAY))
    services.tasks.save(Task("late but done", due=YESTERDAY, done=True))
    services.tasks.save(Task("now", due=TODAY))

    today = services.planner.day_agenda(TODAY)
    assert [(t.task.title, t.overdue) for t in today.tasks] == [("late", True), ("now", False)]
    assert today.open_task_count == 2

    tomorrow = services.planner.day_agenda(TOMORROW)
    assert tomorrow.tasks == ()


def test_week_shows_weekend_only_when_needed(services):
    add_course(services, slots=((0, 540, 600),))
    week = services.planner.week_agenda(TODAY)
    assert len(week.days) == 5
    assert week.monday == date(2026, 9, 21)
    assert week.today_index == 2

    services.planner.save_event(Event(date(2026, 9, 26), TimeRange(600, 660), "Match"))
    assert len(services.planner.week_agenda(TODAY).days) == 7

    next_week = services.planner.week_agenda(TODAY + timedelta(days=7))
    assert next_week.today_index is None
    assert len(next_week.days) == 5


def test_task_groups_in_display_order(services):
    services.tasks.save(Task("undated"))
    services.tasks.save(Task("today", due=TODAY))
    services.tasks.save(Task("late", due=YESTERDAY))
    services.tasks.save(Task("done", due=TODAY, done=True))

    buckets = [g.bucket for g in services.tasks.groups(include_done=True)]
    assert buckets == [DueBucket.OVERDUE, DueBucket.TODAY, DueBucket.UNDATED, DueBucket.DONE]
    assert DueBucket.DONE not in [g.bucket for g in services.tasks.groups(include_done=False)]


def test_task_groups_filter_by_course_and_attach_course(services):
    course_id = add_course(services)
    services.tasks.save(Task("hw", TaskKind.HOMEWORK, course_id, TODAY))
    services.tasks.save(Task("other", due=TODAY))

    (group,) = services.tasks.groups(course_id=course_id)
    (item,) = group.items
    assert item.task.title == "hw" and item.course.name == "Maths"


def test_set_done(services):
    task_id = services.tasks.save(Task("x", due=TODAY))
    services.tasks.set_done(task_id, True)
    assert services.tasks.task(task_id).done


def test_deleting_course_unlinks_but_keeps_tasks_and_notes(services):
    course_id = add_course(services)
    task_id = services.tasks.save(Task("hw", course_id=course_id))
    note = services.notes.create("# n", course_id)

    services.timetable.delete_course(course_id)
    assert services.tasks.task(task_id).course_id is None
    assert services.notes.note(note.id).course_id is None


def test_class_note_is_created_once(services):
    course_id = add_course(services, "Biology")
    first = services.notes.class_note(course_id, TODAY)
    assert first.title == "Biology: Wednesday 23 September 2026"
    assert services.notes.class_note(course_id, TODAY).id == first.id
    assert services.notes.class_note(course_id, TOMORROW).id != first.id


def test_notes_search_pins_first_and_escapes_wildcards(services):
    services.notes.create("# plain")
    pinned = services.notes.create("# pinned 100%")
    pinned.pinned = True
    services.notes.save(pinned)

    assert [n.title for n in services.notes.search()][0] == "pinned 100%"
    assert [n.title for n in services.notes.search("100%")] == ["pinned 100%"]
    assert [n.title for n in services.notes.search("_")] == []


def test_journal_round_trip_and_blank_clears(services):
    services.planner.save_journal(TODAY, "hello")
    assert services.planner.day_agenda(TODAY).journal == "hello"
    services.planner.save_journal(TODAY, "  ")
    assert services.planner.journal(TODAY) == ""


def test_writes_publish_change_topics(services):
    seen = []
    services.bus.subscribe(seen.append)
    course_id = add_course(services)
    services.tasks.save(Task("x"))
    services.planner.save_event(Event(TODAY, TimeRange(1, 2), "e"))
    services.notes.create()
    services.timetable.delete_course(course_id)
    assert seen == [Topic.COURSES, Topic.TASKS, Topic.EVENTS, Topic.NOTES, Topic.COURSES]


def test_next_meeting(services):
    course_id = add_course(services, slots=((0, 540, 600),))
    assert services.timetable.next_meeting(course_id, TODAY) == date(2026, 9, 28)
