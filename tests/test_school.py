from datetime import date, timedelta

import pytest

from quire.application.bus import Topic
from quire.application.errors import AuthenticationError, NotConnected
from quire.application.ports import (
    RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)
from quire.domain import ClassSlot, Course, DueBucket, TaskKind, TimeRange

from .conftest import TODAY

MATHS = RemoteSubject("1", "MATEMATICA", ("ROSSI MARIO",))
HISTORY = RemoteSubject("2", "STORIA", ())


def homework(id="10", day=TODAY + timedelta(days=2), text="Pag. 34 es. 1-5\nripassare",
             subject=MATHS, kind=TaskKind.HOMEWORK):
    return RemoteAssignment(id, day, kind, text, subject.id, subject.name, "BIANCHI ANNA")


def grade(id="g1", value=7.5, display="7½", subject=MATHS, cancelled=False):
    return RemoteGrade(id, TODAY - timedelta(days=3), subject.id, subject.name, display, value,
                       "Scritto", "Trimestre", "", cancelled)


@pytest.fixture
def connected(services, register):
    register.subjects_ = [MATHS, HISTORY]
    services.school.connect("S1234567X", "secret")
    return services


def test_connect_checks_password_before_saving(services, credentials):
    with pytest.raises(AuthenticationError):
        services.school.connect("S1234567X", "nope")
    assert credentials.load() is None
    assert not services.school.status().connected

    services.school.connect(" S1234567X ", "secret")
    status = services.school.status()
    assert status.connected and status.username == "S1234567X"
    assert status.student_name == "Ada Lovelace"
    assert credentials.load().password == "secret"


def test_sync_without_account_raises(services):
    with pytest.raises(NotConnected):
        services.school.sync()


def test_sync_creates_tidy_courses_and_imports_homework(connected, register):
    register.assignments_ = [homework()]
    report = connected.school.sync()

    names = {c.name: c for c in connected.timetable.courses()}
    assert set(names) == {"Matematica", "Storia"}
    assert names["Matematica"].teacher == "Rossi Mario"
    assert report.first_sync and report.courses_created == 2

    (task,) = report.new_tasks
    assert task.title == "Pag. 34 es. 1-5"
    assert task.kind is TaskKind.HOMEWORK
    assert task.course_id == names["Matematica"].id
    assert "ripassare" in task.details and "— Bianchi Anna" in task.details


def test_existing_course_is_adopted_by_name(connected, register, services):
    # A course the student made before connecting keeps its colour and timetable.
    own = Course("Storia", color="#123456", slots=[ClassSlot(0, TimeRange(480, 540))])
    services.timetable.save_course(own)
    connected.school.sync()
    storia = [c for c in connected.timetable.courses() if c.name == "Storia"]
    assert len(storia) == 1
    assert storia[0].color == "#123456" and storia[0].external_id == "classeviva:subject:2"


def test_resync_updates_without_duplicating_and_keeps_done(connected, register):
    register.assignments_ = [homework()]
    connected.school.sync()
    (task,) = connected.tasks.groups()[0].items
    connected.tasks.set_done(task.task.id, True)

    register.assignments_ = [homework(text="Pag. 35 es. 1-8")]
    report = connected.school.sync()
    assert not report.new_tasks and len(report.updated_tasks) == 1
    assert not report.first_sync

    tasks = [i.task for g in connected.tasks.groups(include_done=True) for i in g.items]
    assert len(tasks) == 1
    assert tasks[0].title == "Pag. 35 es. 1-8" and tasks[0].done


def test_assignment_removed_by_teacher_disappears_unless_done(connected, register):
    register.assignments_ = [homework("1"), homework("2", text="Esercizi")]
    connected.school.sync()
    done_id = next(i.task.id for g in connected.tasks.groups() for i in g.items
                   if i.task.title == "Esercizi")
    connected.tasks.set_done(done_id, True)

    register.assignments_ = []
    report = connected.school.sync()
    assert report.removed_tasks == 1
    remaining = [i.task.title for g in connected.tasks.groups(include_done=True) for i in g.items]
    assert remaining == ["Esercizi"]


def test_manual_tasks_are_never_touched_by_sync(connected, register):
    from quire.domain import Task
    connected.tasks.save(Task("My own task", due=TODAY))
    register.assignments_ = []
    connected.school.sync()
    assert [i.task.title for i in connected.tasks.groups()[0].items] == ["My own task"]


def test_new_grades_are_reported_and_averaged(connected, register):
    register.grades_ = [grade("g1", 7.5), grade("g2", None, "ass")]
    first = connected.school.sync()
    assert len(first.new_grades) == 2

    register.grades_ = [grade("g1", 7.5), grade("g2", None, "ass"), grade("g3", 9.0, "9"),
                        grade("g4", 3.0, "3", cancelled=True)]
    second = connected.school.sync()
    assert [g.display for g in second.new_grades] == ["9", "3"]

    (maths,) = connected.school.grades_by_subject()
    assert maths.subject == "Matematica" and maths.course.name == "Matematica"
    assert maths.average == 8.25  # "ass" has no value, cancelled marks don't count
    assert connected.school.overall_average() == 8.25


def test_lessons_are_mirrored_for_recent_days(connected, register):
    register.lessons_ = [
        RemoteLesson("l1", TODAY - timedelta(days=1), "1", "MATEMATICA", "Equazioni", "ROSSI", 2),
        RemoteLesson("l2", TODAY, "2", "STORIA", "Rivoluzione francese", "", 1),
    ]
    connected.school.sync()
    lessons = connected.school.recent_lessons()
    assert [(l.subject, l.topic) for l in lessons] == [
        ("Storia", "Rivoluzione francese"), ("Matematica", "Equazioni")]
    assert lessons[1].teacher == "Rossi"


def test_exam_shows_up_in_coursework_and_today(connected, register):
    register.assignments_ = [homework("9", day=TODAY, text="Verifica capitolo 3",
                                      kind=TaskKind.EXAM)]
    connected.school.sync()
    agenda = connected.planner.day_agenda(TODAY)
    assert [t.task.kind for t in agenda.tasks] == [TaskKind.EXAM]
    assert connected.tasks.groups()[0].bucket is DueBucket.TODAY


def test_disconnect_forgets_account_but_keeps_data(connected, register, credentials):
    register.assignments_ = [homework()]
    connected.school.sync()
    connected.school.disconnect()
    assert credentials.load() is None
    assert not connected.school.status().connected
    assert connected.tasks.groups()


def test_sync_publishes_changes(connected, register):
    seen = []
    connected.bus.subscribe(seen.append)
    connected.school.sync()
    assert Topic.TASKS in seen and Topic.SCHOOL in seen


def own_course(services, name, slots=((0, 480, 540),)):
    return services.timetable.save_course(
        Course(name, color="#123456",
               slots=[ClassSlot(wd, TimeRange(s, e)) for wd, s, e in slots]))


def test_subjects_from_sync_are_offered_for_linking(connected, register):
    connected.school.sync()
    links = {l.subject.name: l for l in connected.school.subject_links()}
    assert set(links) == {"Matematica", "Storia"}
    assert links["Matematica"].course.name == "Matematica"
    assert links["Matematica"].subject.teachers == ("Rossi Mario",)


def test_linking_folds_the_auto_created_duplicate_into_your_course(connected, register):
    maths = own_course(connected, "Maths")
    register.assignments_ = [homework()]
    register.grades_ = [grade("g1", 8.0)]
    connected.school.sync()
    duplicate = next(c for c in connected.timetable.courses() if c.name == "Matematica")
    note = connected.notes.create("# Limits", duplicate.id, "Calculus")

    connected.school.link_course(maths, "classeviva:subject:1")

    names = [c.name for c in connected.timetable.courses()]
    assert "Matematica" not in names and "Maths" in names
    linked = connected.timetable.course(maths)
    assert linked.external_id == "classeviva:subject:1"
    assert linked.teacher == "Rossi Mario" and len(linked.slots) == 1  # your timetable stays
    (task,) = [i.task for g in connected.tasks.groups() for i in g.items]
    assert task.course_id == maths
    assert connected.notes.note(note.id).course_id == maths
    assert connected.school.grades_by_subject()[0].course.id == maths


def test_after_linking_sync_uses_your_course_and_creates_no_duplicate(connected, register):
    maths = own_course(connected, "Maths")
    connected.school.sync()
    connected.school.link_course(maths, "classeviva:subject:1")

    register.assignments_ = [homework("99", text="Nuovi esercizi")]
    report = connected.school.sync()
    assert report.courses_created == 0
    assert [c.name for c in connected.timetable.courses()].count("Matematica") == 0
    assert report.new_tasks[0].course_id == maths


def test_linking_never_deletes_a_course_with_class_times(connected, register):
    connected.school.sync()
    auto = next(c for c in connected.timetable.courses() if c.name == "Matematica")
    auto.slots = [ClassSlot(1, TimeRange(600, 660))]
    connected.timetable.save_course(auto)
    maths = own_course(connected, "Maths")

    connected.school.link_course(maths, "classeviva:subject:1")
    kept = connected.timetable.course(auto.id)
    assert kept.external_id is None and kept.slots


def test_unlinking(connected, register):
    connected.school.sync()
    auto = next(c for c in connected.timetable.courses() if c.name == "Storia")
    connected.school.link_course(auto.id, None)
    assert connected.timetable.course(auto.id).external_id is None
    links = {l.subject.name: l.course for l in connected.school.subject_links()}
    assert links["Storia"] is None


def test_linking_to_unknown_subject_fails(connected, register):
    from quire.domain import NotFound
    maths = own_course(connected, "Maths")
    with pytest.raises(NotFound):
        connected.school.link_course(maths, "classeviva:subject:404")
