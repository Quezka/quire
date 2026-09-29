"""Two devices syncing through one (fake) cloud account."""
import time
from datetime import timedelta

import pytest

from quire.application.bus import Topic
from quire.application.errors import CloudAuthError, SyncError, SyncNotSetUp, ValidationError
from quire.application.inputs import (
    CourseInput, EventInput, JobInput, NoteInput, PatternInput, ShiftInput, SlotInput, TaskInput,
)
from quire.application.types import TaskKind
from quire.bootstrap import build_services
from quire.infrastructure.credentials import MemoryCredentialStore

from .conftest import TODAY, FixedClock
from .fakes import FakeCloud, FakeRegister

CONFIG = ("quire-sync-test", "AIzaSyTESTKEY-0123456789abcdef")
EMAIL, PASSWORD = "me@example.com", "secret123"


@pytest.fixture
def shared_cloud():
    return FakeCloud()


def device(tmp_path, cloud, name):
    services, db = build_services(tmp_path / f"{name}.db", FixedClock(), FakeRegister(),
                                  MemoryCredentialStore(), cloud, MemoryCredentialStore())
    return services, db


def connect(services, create=False, take_cloud_copy=False):
    config = services.sync.check(*CONFIG, EMAIL, PASSWORD)
    session = services.sync.authenticate(config, EMAIL, PASSWORD, create)
    services.sync.connect(config, session, take_cloud_copy)


@pytest.fixture
def pair(tmp_path, shared_cloud):
    a, db_a = device(tmp_path, shared_cloud, "laptop")
    b, db_b = device(tmp_path, shared_cloud, "desktop")
    connect(a, create=True)
    connect(b)
    yield a, b
    db_a.close()
    db_b.close()


def tick():
    time.sleep(0.003)  # change times have millisecond precision


def titles(services):
    return sorted(i.task.title for g in services.tasks.groups(include_done=True) for i in g.items)


def test_everything_reaches_the_other_device(pair):
    a, b = pair
    maths = a.timetable.save_course(None, CourseInput("Maths", "Rossi", "B12", "#123456",
                                                      (SlotInput(0, 480, 540, "Lab"),)))
    a.tasks.save(None, TaskInput("Problem set", TaskKind.HOMEWORK, maths, TODAY, "p. 12"))
    a.notes.create("# Derivatives", maths, "Calculus")
    a.planner.save_event(None, EventInput(TODAY, 600, 660, "Dentist"))
    a.planner.save_journal(TODAY, "Good day")
    job = a.work.save_job(None, JobInput("Pizzeria", "#f76b15", 9.0, 10.0),
                          weekly=[PatternInput(4, 18 * 60, 22 * 60, 30)])
    a.work.save_shift(None, ShiftInput(job, TODAY, 12 * 60, 14 * 60))
    a.work.skip_occurrence(job, TODAY + timedelta(days=2), 18 * 60)

    assert a.sync.sync().sent >= 7
    result = b.sync.sync()
    assert result.received >= 7

    (course,) = b.timetable.courses()
    assert (course.name, course.teacher, course.room, course.color) == (
        "Maths", "Rossi", "B12", "#123456")
    assert [(s.weekday, s.time.start, s.room) for s in course.slots] == [(0, 480, "Lab")]
    (item,) = [i for g in b.tasks.groups() for i in g.items]
    assert item.task.title == "Problem set" and item.course.name == "Maths"
    assert item.task.details == "p. 12" and item.task.kind is TaskKind.HOMEWORK
    (synced_note,) = b.notes.search()
    assert synced_note.title == "Derivatives" and synced_note.topic == "Calculus"
    assert synced_note.course.id == course.id  # linked to B's own copy of the course
    assert [i.title for i in b.planner.day_agenda(TODAY).items
            if i.kind.value == "event"] == ["Dentist"]
    assert b.planner.journal(TODAY) == "Good day"
    (b_job,) = b.work.jobs()
    assert (b_job.hourly_rate, b_job.deductions, len(b_job.weekly)) == (9.0, 10.0, 1)
    shifts = b.work.shifts_between(TODAY, TODAY + timedelta(days=7))
    assert {(s.shift.day, s.shift.start) for s in shifts} >= {(TODAY, 12 * 60)}
    assert (TODAY + timedelta(days=2), 18 * 60) not in {(s.shift.day, s.shift.start)
                                                        for s in shifts}  # the skip synced


def test_nothing_is_sent_twice_and_applied_changes_are_not_echoed(pair, shared_cloud):
    a, b = pair
    a.tasks.save(None, TaskInput("Essay"))
    a.sync.sync()
    b.sync.sync()
    assert b.sync.status().pending == 0  # what B received isn't "changed on B"
    pushes = shared_cloud.pushes
    assert a.sync.sync().sent == 0 and b.sync.sync().sent == 0
    assert shared_cloud.pushes == pushes


def test_edits_and_deletions_travel_both_ways(pair):
    a, b = pair
    task_id = a.tasks.save(None, TaskInput("Essay"))
    a.sync.sync()
    b.sync.sync()
    (on_b,) = [i.task for g in b.tasks.groups() for i in g.items]
    tick()
    b.tasks.set_done(on_b.id, True)
    b.sync.sync()
    a.sync.sync()
    assert a.tasks.task(task_id).done

    tick()
    a.tasks.delete(task_id)
    a.sync.sync()
    b.sync.sync()
    assert titles(b) == []


def test_newer_change_wins_a_conflict(pair):
    a, b = pair
    task_id = a.tasks.save(None, TaskInput("Essay"))
    a.sync.sync()
    b.sync.sync()
    (on_b,) = [i.task for g in b.tasks.groups() for i in g.items]

    tick()
    a.tasks.save(task_id, TaskInput("Essay: first draft"))  # older
    tick()
    b.tasks.save(on_b.id, TaskInput("Essay: final"))  # newer
    a.sync.sync()
    b.sync.sync()  # B's version is newer: it's kept and sent
    a.sync.sync()
    assert titles(a) == titles(b) == ["Essay: final"]


def test_a_deletion_loses_to_a_newer_edit(pair):
    a, b = pair
    task_id = a.tasks.save(None, TaskInput("Essay"))
    a.sync.sync()
    b.sync.sync()
    (on_b,) = [i.task for g in b.tasks.groups() for i in g.items]
    tick()
    a.tasks.delete(task_id)
    tick()
    b.tasks.save(on_b.id, TaskInput("Essay, still needed"))
    a.sync.sync()
    b.sync.sync()
    a.sync.sync()
    assert titles(a) == titles(b) == ["Essay, still needed"]


def test_deleting_a_course_keeps_the_other_devices_tasks_unlinked(pair):
    a, b = pair
    maths = a.timetable.save_course(None, CourseInput("Maths"))
    a.tasks.save(None, TaskInput("Homework", course_id=maths))
    a.sync.sync()
    b.sync.sync()
    tick()
    a.timetable.delete_course(maths)
    a.sync.sync()
    b.sync.sync()
    assert b.timetable.courses() == []
    (item,) = [i for g in b.tasks.groups() for i in g.items]
    assert item.task.title == "Homework" and item.course is None


def test_a_shift_waits_for_its_job(pair, shared_cloud):
    a, b = pair
    job = a.work.save_job(None, JobInput("Café"))
    a.work.save_shift(None, ShiftInput(job, TODAY, 600, 660))
    a.sync.sync()
    # Pretend the job's document hasn't reached B yet.
    user = f"user-{EMAIL}"
    job_doc = next(k for k in shared_cloud.docs if k[0] == user and k[1] == "job")
    held = shared_cloud.docs.pop(job_doc)
    b.sync.sync()
    assert b.work.shifts_between(TODAY, TODAY) == []
    shared_cloud.clock += 1
    shared_cloud.docs[job_doc] = (shared_cloud.clock, held[1])
    b.sync.sync()
    (shift,) = b.work.shifts_between(TODAY, TODAY)
    assert shift.job.name == "Café"


def test_register_imports_are_the_same_record_on_every_device(pair):
    a, b = pair
    # Both devices imported the same Classeviva homework before syncing.
    for services in (a, b):
        task_id = services.tasks.save(None, TaskInput("Esercizi", TaskKind.HOMEWORK))
        stored = services.tasks._tasks.get(task_id)
        stored.external_id = "classeviva:homework:77"
        services.tasks._tasks.update(stored)
    a.sync.sync()
    b.sync.sync()
    a.sync.sync()
    assert titles(a) == titles(b) == ["Esercizi"]


def test_second_device_can_take_the_cloud_copy(tmp_path, shared_cloud):
    a, db_a = device(tmp_path, shared_cloud, "laptop")
    b, db_b = device(tmp_path, shared_cloud, "desktop")
    try:
        a.timetable.save_course(None, CourseInput("Maths"))
        connect(a, create=True)
        a.sync.sync()
        b.timetable.save_course(None, CourseInput("Maths"))  # typed in twice
        connect(b, take_cloud_copy=True)
        b.sync.sync()
        assert [c.name for c in b.timetable.courses()] == ["Maths"]
        a.sync.sync()
        assert [c.name for c in a.timetable.courses()] == ["Maths"]  # nothing was deleted
    finally:
        db_a.close()
        db_b.close()


def test_views_refresh_after_a_sync(pair):
    a, b = pair
    a.notes.create("# Hello")
    a.sync.sync()
    seen = []
    b.bus.subscribe(seen.append)
    b.sync.sync()
    assert seen == [Topic.NOTES]


def test_existing_data_is_sent_the_first_time(tmp_path, shared_cloud):
    a, db_a = device(tmp_path, shared_cloud, "laptop")
    b, db_b = device(tmp_path, shared_cloud, "desktop")
    try:
        a.notes.update(a.notes.create("# Old").id, NoteInput("# Old", pinned=True))
        assert a.sync.status().pending == 1 and not a.sync.status().set_up
        connect(a, create=True)
        a.sync.sync()
        connect(b)
        b.sync.sync()
        (note,) = b.notes.search()
        assert note.pinned
    finally:
        db_a.close()
        db_b.close()


def test_status_problems_and_sign_out(pair, shared_cloud):
    a, _b = pair
    status = a.sync.status()
    assert status.set_up and status.email == EMAIL and status.project_id == CONFIG[0]
    shared_cloud.offline = True
    with pytest.raises(SyncError):
        a.sync.sync()
    assert "internet" in a.sync.status().problem
    shared_cloud.offline = False
    a.sync.sync()
    assert a.sync.status().problem == "" and a.sync.status().last_sync is not None

    a.sync.disconnect()
    assert not a.sync.status().set_up
    with pytest.raises(SyncNotSetUp):
        a.sync.sync()


def test_a_dead_sign_in_asks_to_set_up_again(pair, shared_cloud):
    a, _b = pair
    shared_cloud.accounts.clear()  # e.g. the account was deleted in the console
    with pytest.raises(CloudAuthError):
        a.sync.sync()
    assert not a.sync.status().set_up


def test_setup_checks_its_inputs(services):
    with pytest.raises(ValidationError):
        services.sync.check("My Project", CONFIG[1], EMAIL, PASSWORD)
    with pytest.raises(ValidationError):
        services.sync.check(CONFIG[0], "short", EMAIL, PASSWORD)
    with pytest.raises(ValidationError):
        services.sync.check(CONFIG[0], CONFIG[1], "not-an-email", PASSWORD)
    with pytest.raises(ValidationError):
        services.sync.check(CONFIG[0], CONFIG[1], EMAIL, "")
    assert services.sync.check(f" {CONFIG[0]} ", CONFIG[1], EMAIL, "x").project_id == CONFIG[0]


def test_wrong_password_and_existing_account(services, cloud):
    config = services.sync.check(*CONFIG, EMAIL, PASSWORD)
    services.sync.authenticate(config, EMAIL, PASSWORD, create=True)
    with pytest.raises(CloudAuthError):
        services.sync.authenticate(config, EMAIL, PASSWORD, create=True)
    with pytest.raises(CloudAuthError):
        services.sync.authenticate(config, EMAIL, "wrong", create=False)


def test_the_phone_setup_code_carries_the_sign_in_and_optionally_the_register(tmp_path,
                                                                             shared_cloud):
    import base64
    import json

    from quire.application.errors import SyncNotSetUp
    from quire.application.ports import Credentials

    services, db = device(tmp_path, shared_cloud, "a")
    with pytest.raises(SyncNotSetUp):
        services.sync.phone_link()
    connect(services, create=True)
    link = services.sync.phone_link()
    assert link.startswith("quire-link:")
    body = link.removeprefix("quire-link:")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    # The fields the phone reads (android sync/DeviceLink.kt).
    assert data["v"] == "1" and data["project"] and data["api_key"] and data["refresh"]
    assert "cv_user" not in data
    with_school = services.sync.phone_link(Credentials("S1234567X", "pw"))
    body = with_school.removeprefix("quire-link:")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    assert (data["cv_user"], data["cv_pass"]) == ("S1234567X", "pw")
    db.close()
