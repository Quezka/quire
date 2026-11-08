from datetime import date, timedelta

import pytest

from quire.application.bus import Topic
from quire.application.dto import ItemKind
from quire.application.errors import NotFound, ValidationError
from quire.application.inputs import (
    CourseInput, EventInput, NotebookInput, NoteInput, RoutineInput, SleepInput, SlotInput, TaskInput, WaterProfileInput,
)
from quire.application.types import DueBucket, TaskKind

from .conftest import TODAY

YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


def add_course(services, name="Maths", slots=((2, 540, 600),), color="#4f7cff"):
    course = CourseInput(name, color=color,
                         slots=tuple(SlotInput(wd, s, e) for wd, s, e in slots))
    return services.timetable.save_course(None, course)


def test_course_round_trip_keeps_slots(services):
    course_id = add_course(services, slots=((0, 540, 600), (2, 600, 660)))
    course = services.timetable.course(course_id)
    assert [(s.weekday, s.time.start) for s in course.slots] == [(0, 540), (2, 600)]

    services.timetable.save_course(course_id, CourseInput(course.name, slots=(
        SlotInput(0, 540, 600),)))
    assert len(services.timetable.course(course_id).slots) == 1


def test_invalid_course_is_not_stored(services):
    with pytest.raises(ValidationError):
        services.timetable.save_course(None, CourseInput(""))
    assert services.timetable.courses() == []


def test_missing_entities_raise_not_found(services):
    with pytest.raises(NotFound):
        services.timetable.course(99)
    with pytest.raises(NotFound):
        services.tasks.task(99)


def test_day_agenda_merges_classes_and_events_in_time_order(services):
    add_course(services, "Maths", ((2, 600, 660),))
    services.planner.save_event(None, EventInput(TODAY, 480, 510, "Breakfast"))
    services.planner.save_event(None, EventInput(TOMORROW, 480, 510, "Not today"))

    agenda = services.planner.day_agenda(TODAY)
    assert [(i.kind, i.title) for i in agenda.items] == [
        (ItemKind.EVENT, "Breakfast"), (ItemKind.CLASS, "Maths")]
    assert agenda.is_today and agenda.has_courses


def test_milestone_is_a_one_minute_event_that_ignores_the_end(services):
    services.planner.save_event(None, EventInput(TODAY, 360, 900, "Wake up", milestone=True))
    services.planner.save_event(None, EventInput(TODAY, 1439, 0, "Last call", milestone=True))
    services.planner.save_event(None, EventInput(TODAY, 480, 510, "Breakfast"))

    items = {i.title: i for i in services.planner.day_agenda(TODAY).items}
    wake = items["Wake up"]
    assert (wake.time.start, wake.time.end) == (360, 361) and wake.is_milestone
    assert items["Last call"].time.end == 1440 and items["Last call"].is_milestone
    assert not items["Breakfast"].is_milestone
    assert services.planner.event(wake.ref_id).is_milestone


def test_routine_repeats_on_its_weekdays_as_a_milestone(services):
    # TODAY is a Wednesday (2); the routine runs Monday to Friday.
    rid = services.planner.save_routine(None, RoutineInput("Wake up", 360, (0, 1, 2, 3, 4)))
    weekend = TODAY + timedelta(days=3)  # Saturday

    on_wednesday = [i for i in services.planner.day_agenda(TODAY).items if i.title == "Wake up"]
    assert len(on_wednesday) == 1
    item = on_wednesday[0]
    assert item.kind is ItemKind.ROUTINE and item.ref_id == rid and item.is_milestone
    assert (item.time.start, item.time.end) == (360, 361)
    assert services.planner.day_agenda(weekend).items == ()
    assert any(i.title == "Wake up" for i in services.planner.items_between(TODAY, TODAY))
    week = services.planner.week_agenda(TODAY)
    assert sum(i.title == "Wake up" for i in week.items) == 5

    services.planner.save_routine(rid, RoutineInput("Wake up", 390, (5,)))
    assert services.planner.routine(rid).minute == 390
    assert [i.title for i in services.planner.day_agenda(weekend).items] == ["Wake up"]
    services.planner.delete_routine(rid)
    assert services.planner.routines() == []


def test_sleep_log_goal_and_overview(services):
    sleep = services.sleep
    assert sleep.goal() == (8.0, 6 * 60)
    sleep.save_goal(7.5, 7 * 60)
    assert sleep.goal() == (7.5, 7 * 60)

    sleep.save(SleepInput(TODAY, 23 * 60, 6 * 60 + 30, 4, " woke twice "))
    sleep.save(SleepInput(YESTERDAY, 1 * 60, 8 * 60))
    sleep.save(SleepInput(TODAY, 23 * 60 + 30, 7 * 60, 5))  # the same night, corrected
    last = sleep.night(TODAY)
    assert (last.asleep, last.woke, last.minutes, last.quality) == (23 * 60 + 30, 7 * 60, 450, 5)

    overview = sleep.overview()
    assert [n.day for n in overview.nights] == [YESTERDAY, TODAY]
    assert overview.bedtime_goal == 23 * 60 + 30 - 0  # 07:00 minus 7.5 h
    assert overview.average_minutes == (450 + 420) // 2 and overview.enough == 2
    sleep.delete(TODAY)
    assert sleep.night(TODAY) is None
    with pytest.raises(ValidationError):
        sleep.save(SleepInput(TODAY, 600, 610))


def test_water_goal_log_undo_and_reminders(services):
    water = services.water
    assert water.overview().goal is None and water.reminder() is None  # no profile yet
    assert water.save_profile(WaterProfileInput(175, 70, 300)) == 2200
    water.add(300)
    water.add(250)
    o = water.overview()
    assert (o.goal, o.drunk, [e.ml for e in o.entries]) == (2200, 550, [300, 250])
    assert o.profile.glass_ml == 300 and o.week[-1] == (TODAY, 550) and len(o.week) == 7
    water.undo_last()
    assert water.overview().drunk == 300
    water.delete(water.overview().entries[0].id)
    assert water.overview().drunk == 0

    # The fixed test clock says 12:00: 800 ml behind pace on an empty day, so it speaks once.
    assert water.reminder() == "0/2200"
    assert water.reminder() is None  # not again within 90 minutes
    water.save_profile(WaterProfileInput(175, 70, 250, remind=False))
    assert services.water.profile().remind is False
    for bad in (WaterProfileInput(10, 70), WaterProfileInput(175, 70, 5), WaterProfileInput(175, 70, 250, True, 900, 600)):
        with pytest.raises(ValidationError):
            water.save_profile(bad)
    with pytest.raises(ValidationError):
        water.add(5000)


def test_routine_needs_a_title_and_a_day(services):
    with pytest.raises(ValidationError):
        services.planner.save_routine(None, RoutineInput(" ", 360))
    with pytest.raises(ValidationError):
        services.planner.save_routine(None, RoutineInput("Run", 360, ()))


def test_overdue_tasks_only_follow_you_to_today(services):
    services.tasks.save(None, TaskInput("late", due=YESTERDAY))
    services.tasks.save(None, TaskInput("late but done", due=YESTERDAY, done=True))
    services.tasks.save(None, TaskInput("now", due=TODAY))

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

    services.planner.save_event(None, EventInput(date(2026, 9, 26), 600, 660, "Match"))
    assert len(services.planner.week_agenda(TODAY).days) == 7

    next_week = services.planner.week_agenda(TODAY + timedelta(days=7))
    assert next_week.today_index is None
    assert len(next_week.days) == 5


def test_task_groups_in_display_order(services):
    services.tasks.save(None, TaskInput("undated"))
    services.tasks.save(None, TaskInput("today", due=TODAY))
    services.tasks.save(None, TaskInput("late", due=YESTERDAY))
    services.tasks.save(None, TaskInput("done", due=TODAY, done=True))

    buckets = [g.bucket for g in services.tasks.groups(include_done=True)]
    assert buckets == [DueBucket.OVERDUE, DueBucket.TODAY, DueBucket.UNDATED, DueBucket.DONE]
    assert DueBucket.DONE not in [g.bucket for g in services.tasks.groups(include_done=False)]


def test_task_groups_filter_by_course_and_attach_course(services):
    course_id = add_course(services)
    services.tasks.save(None, TaskInput("hw", TaskKind.HOMEWORK, course_id, TODAY))
    services.tasks.save(None, TaskInput("other", due=TODAY))

    (group,) = services.tasks.groups(course_id=course_id)
    (item,) = group.items
    assert item.task.title == "hw" and item.course.name == "Maths"


def test_set_done(services):
    task_id = services.tasks.save(None, TaskInput("x", due=TODAY))
    services.tasks.set_done(task_id, True)
    assert services.tasks.task(task_id).done


def test_deleting_course_unlinks_but_keeps_tasks_and_notes(services):
    course_id = add_course(services)
    task_id = services.tasks.save(None, TaskInput("hw", course_id=course_id))
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
    services.notes.update(pinned.id, NoteInput(pinned.body, pinned=True))

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
    services.tasks.save(None, TaskInput("x"))
    services.planner.save_event(None, EventInput(TODAY, 1, 2, "e"))
    services.notes.create()
    services.timetable.delete_course(course_id)
    assert seen == [Topic.COURSES, Topic.TASKS, Topic.EVENTS, Topic.NOTES, Topic.COURSES]


def test_next_meeting(services):
    course_id = add_course(services, slots=((0, 540, 600),))
    assert services.timetable.next_meeting(course_id, TODAY) == date(2026, 9, 28)


def test_notes_group_by_course_then_topic(services):
    bio = add_course(services, "Biology")
    art = add_course(services, "Art")
    notes = services.notes
    notes.create("# Krebs cycle", bio, "Cell respiration")
    notes.create("# Glycolysis", bio, "  cell   respiration ".title())
    notes.create("# DNA", bio, "Genetics")
    notes.create("# Loose biology note", bio)
    notes.create("# Perspective", art, "Drawing")
    notes.create("# Shopping list")

    groups = notes.grouped()
    assert [(g.course.name if g.course else None, g.topic, len(g.notes)) for g in groups] == [
        ("Art", "Drawing", 1),
        ("Biology", "Cell respiration", 2),  # the second note adopted the first spelling
        ("Biology", "Genetics", 1),
        ("Biology", "", 1),
        (None, "", 1),
    ]
    only_bio = notes.grouped(course_id=bio)
    assert {g.course.name for g in only_bio} == {"Biology"}
    assert [g.topic for g in notes.grouped("krebs")] == ["Cell respiration"]


def test_topic_suggestions_are_per_course(services):
    bio = add_course(services, "Biology")
    services.notes.create("# a", bio, "Genetics")
    services.notes.create("# b", bio, "ecology")
    services.notes.create("# c", None, "Personal")
    assert services.notes.topics(bio) == ["ecology", "Genetics"]
    assert services.notes.topics(None) == ["Personal"]


def test_search_matches_topic(services):
    services.notes.create("# Unrelated body", None, "Photosynthesis")
    assert [n.topic for n in services.notes.search("photo")] == ["Photosynthesis"]


def test_rename_topic_moves_every_note_in_that_course_only(services):
    bio = add_course(services, "Biology")
    chem = add_course(services, "Chemistry")
    a = services.notes.create("# a", bio, "Cells")
    b = services.notes.create("# b", bio, "Cells")
    other = services.notes.create("# c", chem, "Cells")
    before = services.notes.note(a.id).updated

    assert services.notes.rename_topic(bio, "Cells", " Cell  biology ") == 2
    assert services.notes.note(a.id).topic == "Cell biology"
    assert services.notes.note(b.id).topic == "Cell biology"
    assert services.notes.note(other.id).topic == "Cells"
    assert services.notes.note(a.id).updated == before
    assert services.notes.rename_topic(bio, "", "x") == 0


def test_saving_a_note_normalises_its_topic(services):
    note = services.notes.create("# n")
    saved = services.notes.update(note.id, NoteInput(note.body, topic="  Mixed   spacing "))
    assert saved.topic == "Mixed spacing"
    assert services.notes.note(note.id).topic == "Mixed spacing"


def test_editing_a_task_keeps_what_the_editor_does_not_show(services):
    course_id = add_course(services)
    task_id = services.tasks.save(None, TaskInput("hw", TaskKind.HOMEWORK, course_id, TODAY))
    stored = services.tasks._tasks.get(task_id)
    stored.external_id = "classeviva:agenda:1"
    services.tasks._tasks.update(stored)

    services.tasks.save(task_id, TaskInput("hw, pages 4-5", TaskKind.HOMEWORK, course_id, TODAY))
    task = services.tasks.task(task_id)
    assert task.title == "hw, pages 4-5" and task.imported


def test_editing_a_course_keeps_its_register_link(services):
    course_id = add_course(services)
    stored = services.timetable._courses.get(course_id)
    stored.external_id = "classeviva:subject:1"
    services.timetable._courses.update(stored)

    services.timetable.save_course(course_id, CourseInput("Mathematics"))
    assert services.timetable.course(course_id).external_id == "classeviva:subject:1"


def test_use_cases_hand_out_read_only_records(services):
    task_id = services.tasks.save(None, TaskInput("x"))
    task = services.tasks.task(task_id)
    with pytest.raises(AttributeError):
        task.title = "changed"


# ---- notebooks: groups of notes that aren't classes --------------------------------------

def test_notebooks_are_created_renamed_and_listed(services):
    seen = []
    services.bus.subscribe(seen.append)
    ideas = services.notes.create_notebook(NotebookInput("  Ideas ", "#f76b15"))
    trips = services.notes.create_notebook(NotebookInput("Trips"))
    assert (ideas.name, ideas.color) == ("Ideas", "#f76b15")
    assert [n.name for n in services.notes.notebooks()] == ["Ideas", "Trips"]
    services.notes.update_notebook(trips.id, NotebookInput("Travel", "#30a46c"))
    assert [(n.name, n.color) for n in services.notes.notebooks()] == [
        ("Ideas", "#f76b15"), ("Travel", "#30a46c")]
    assert Topic.NOTES in seen
    with pytest.raises(ValidationError):
        services.notes.create_notebook(NotebookInput("   "))
    with pytest.raises(NotFound):
        services.notes.update_notebook(999, NotebookInput("x"))


def test_a_note_can_be_filed_in_a_notebook_instead_of_a_class(services):
    ideas = services.notes.create_notebook(NotebookInput("Ideas")).id
    maths = add_course(services)
    note = services.notes.create("# Idea", notebook_id=ideas)
    assert note.notebook_id == ideas and note.course_id is None
    assert [n.id for n in services.notes.search(notebook_id=ideas)] == [note.id]
    assert services.notes.search(course_id=maths) == []
    summary = services.notes.search()[0]
    assert summary.notebook.name == "Ideas" and summary.course is None
    assert services.notes.notebooks()[0].notes == 1

    moved = services.notes.update(note.id, NoteInput(note.body, course_id=maths))
    assert (moved.course_id, moved.notebook_id) == (maths, None)
    back = services.notes.update(note.id, NoteInput(note.body, notebook_id=ideas))
    assert (back.course_id, back.notebook_id) == (None, ideas)


def test_a_note_cannot_be_in_a_class_and_a_notebook(services):
    ideas = services.notes.create_notebook(NotebookInput("Ideas")).id
    maths = add_course(services)
    with pytest.raises(ValidationError):
        services.notes.create("# both", maths, notebook_id=ideas)
    note = services.notes.create("# n")
    with pytest.raises(ValidationError):
        services.notes.update(note.id, NoteInput("# n", maths, notebook_id=ideas))
    with pytest.raises(NotFound):
        services.notes.create("# nowhere", notebook_id=999)


def test_deleting_a_notebook_keeps_its_notes_unfiled(services):
    ideas = services.notes.create_notebook(NotebookInput("Ideas")).id
    note = services.notes.create("# keep me", notebook_id=ideas, topic="Apps")
    services.notes.delete_notebook(ideas)
    assert services.notes.notebooks() == []
    kept = services.notes.note(note.id)
    assert kept.notebook_id is None and kept.body == "# keep me"


def test_notes_group_classes_first_then_notebooks_then_the_rest(services):
    bio = add_course(services, "Biology")
    zoo = services.notes.create_notebook(NotebookInput("Zoo trips")).id
    ideas = services.notes.create_notebook(NotebookInput("Ideas")).id
    notes = services.notes
    notes.create("# Cells", bio, "Cell biology")
    notes.create("# App", topic="ignored-in-none")
    notes.create("# Otters", topic="Otters", notebook_id=zoo)
    notes.create("# Pandas", topic="Pandas", notebook_id=zoo)
    notes.create("# Game", notebook_id=ideas)

    groups = notes.grouped()
    home = lambda g: (g.course.name if g.course else g.notebook.name if g.notebook else None)
    assert [(home(g), g.topic) for g in groups] == [
        ("Biology", "Cell biology"), ("Ideas", ""), ("Zoo trips", "Otters"),
        ("Zoo trips", "Pandas"), (None, "ignored-in-none")]
    assert {home(g) for g in notes.grouped(notebook_id=zoo)} == {"Zoo trips"}


def test_topics_belong_to_their_notebook(services):
    zoo = services.notes.create_notebook(NotebookInput("Zoo")).id
    ideas = services.notes.create_notebook(NotebookInput("Ideas")).id
    bio = add_course(services, "Biology")
    services.notes.create("# a", topic="Otters", notebook_id=zoo)
    services.notes.create("# b", topic="Apps", notebook_id=ideas)
    services.notes.create("# c", bio, "Cells")
    assert services.notes.topics(None, zoo) == ["Otters"]
    assert services.notes.topics(None, ideas) == ["Apps"]
    assert services.notes.topics(bio) == ["Cells"]
    assert services.notes.topics(None) == []
    # reusing a topic's spelling works inside a notebook, and renaming stays inside it
    again = services.notes.create("# d", topic="otters", notebook_id=zoo)
    assert again.topic == "Otters"
    other = services.notes.create("# e", topic="Otters", notebook_id=ideas)
    assert services.notes.rename_topic(None, "Otters", "Sea otters", zoo) == 2
    assert services.notes.note(other.id).topic == "Otters"


def _medicine_services():
    from quire.application.bus import ChangeBus
    from quire.application.services import MedicineService
    from quire.infrastructure.repositories import SqliteMedicineRepository
    from quire.infrastructure.sqlite import SqliteDatabase
    from datetime import datetime

    class Clock:
        moment = datetime(2026, 11, 4, 9, 0)  # a Wednesday

        def now(self):
            return self.moment

        def today(self):
            return self.moment.date()

    clock = Clock()
    return MedicineService(SqliteMedicineRepository(SqliteDatabase(":memory:")), clock, ChangeBus()), clock


def test_medicine_plan_ticks_late_and_reminders():
    from quire.application.inputs import MedicineInput
    svc, clock = _medicine_services()
    vit = svc.save(None, MedicineInput("Vitamin D", "1 tablet", (8 * 60, 20 * 60)))
    svc.save(None, MedicineInput("Thursday only", "", (9 * 60,), (3,)))
    doses = svc.day()
    assert [(d.name, d.planned) for d in doses] == [("Vitamin D", 480), ("Vitamin D", 1200)]
    assert [d.medicine_id for d in svc.due()] == [vit]
    assert svc.due() == []  # each dose nudges once
    assert not svc.day()[0].late  # 09:00 is exactly an hour after
    clock.moment = clock.moment.replace(hour=9, minute=30)
    assert svc.day()[0].late
    svc.mark(vit, clock.today(), 480)
    first = svc.day()[0]
    assert first.done and first.taken and first.at == 9 * 60 + 30 and not first.late
    svc.mark(vit, clock.today(), 480, taken=False)  # changed, not doubled
    assert len(svc.day()) == 2 and svc.day()[0].done and not svc.day()[0].taken
    svc.unmark(vit, clock.today(), 480)
    assert not svc.day()[0].done


def test_pending_doses_put_the_next_one_first_and_drop_ticked_ones():
    from quire.application.inputs import MedicineInput
    svc, clock = _medicine_services()
    vit = svc.save(None, MedicineInput("Vitamin D", "1 tablet", (20 * 60, 8 * 60)))
    iron = svc.save(None, MedicineInput("Iron", "", (12 * 60,)))
    assert [(d.medicine_id, d.planned) for d in svc.pending()] == [(vit, 480), (iron, 720), (vit, 1200)]
    svc.mark(vit, clock.today(), 480)
    assert [(d.medicine_id, d.planned) for d in svc.pending()] == [(iron, 720), (vit, 1200)]


def test_a_stopped_medicine_keeps_what_you_ticked_and_the_week_counts_only_what_was_due():
    from dataclasses import replace
    from datetime import timedelta
    from quire.application.inputs import MedicineInput
    svc, clock = _medicine_services()
    m = svc.save(None, MedicineInput("A", "", (8 * 60, 20 * 60)))
    svc.mark(m, clock.today(), 480)
    assert (svc.week().planned, svc.week().taken) == (7 * 2 - 1, 1)  # tonight's isn't due yet
    svc.save(m, MedicineInput("A", "", (8 * 60, 20 * 60), active=False))
    assert [d.done for d in svc.day()] == [True]  # the ticked one stays on the day
    assert svc.day(clock.today() + timedelta(days=1)) == []


def test_medicine_rules_refuse_nonsense():
    import pytest
    from quire.application.inputs import MedicineInput
    from quire.domain import ValidationError
    svc, _clock = _medicine_services()
    for bad in (MedicineInput(" "), MedicineInput("A", "", (480, 480)), MedicineInput("A", "", (2000,))):
        with pytest.raises(ValidationError):
            svc.save(None, bad)


def test_money_parses_every_way_of_writing_it():
    import pytest
    from quire.domain import ValidationError
    from quire.domain.finance import parse_cents
    for text, cents in (("12,50", 1250), ("12.5", 1250), ("1.234,56", 123456), ("1,234.56", 123456), ("1234", 123400),
                        ("€ 3", 300), ("0,05", 5), (",5", 50), ("1.234", 123400)):
        assert parse_cents(text) == cents, text
    for bad in ("", "abc", "1,2,x"):
        with pytest.raises(ValidationError):
            parse_cents(bad)


def _finance():
    from datetime import date, datetime
    from quire.application.bus import ChangeBus
    from quire.application.services import FinanceService
    from quire.infrastructure.repositories import SqliteTransactionRepository
    from quire.infrastructure.sqlite import SqliteDatabase

    class Settings(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

        def set(self, key, value):
            self[key] = value

    class Clock:
        def now(self):
            return datetime(2026, 11, 4, 9, 0)

        def today(self):
            return date(2026, 11, 4)

    return FinanceService(SqliteTransactionRepository(SqliteDatabase(":memory:")), Settings(), Clock(), ChangeBus())


def test_a_month_adds_up_exactly_by_category_and_against_the_budget():
    from datetime import date
    import pytest
    from quire.application.inputs import TransactionInput as T
    from quire.domain import ValidationError
    svc = _finance()
    svc.add(T(date(2026, 11, 1), "1000", income=True, category="Pay"))
    svc.add(T(date(2026, 11, 2), "0,10", category="Food"))
    svc.add(T(date(2026, 11, 2), "0,20", category="Food"))
    svc.add(T(date(2026, 11, 3), "50", category="Rent"))
    svc.add(T(date(2026, 10, 31), "999", category="Food"))  # another month
    o = svc.month(2026, 11)
    assert (o.income, o.spent, o.balance) == (100000, 5030, 94970)  # 0,10 + 0,20 is exactly 0,30
    assert o.categories == (("Rent", 5000), ("Food", 30))
    assert [t.day.day for t in o.transactions] == [3, 2, 2, 1]
    assert svc.categories()[0] == "Food"
    svc.set_budget("40,00")
    assert svc.month(2026, 11).budget == 4000
    svc.set_budget("")
    assert svc.month(2026, 11).budget is None
    with pytest.raises(ValidationError):
        svc.add(T(date(2026, 11, 3), "0"))
    assert svc.csv(2026, 11)[1] == ["2026-11-01", "1000.00", "Pay", ""]
    assert svc.csv(2026, 11)[2][1] == "-0.10"


def test_the_agenda_becomes_a_calendar_file_with_stable_ids(tmp_path):
    from datetime import date, datetime
    from quire.application.inputs import EventInput
    from quire.bootstrap import build_services
    from quire.domain.ical import CalendarEntry, to_ics
    from quire.infrastructure.system_calendar import EvolutionCalendar
    from quire.infrastructure.credentials import MemoryCredentialStore
    from .fakes import FakeRegister

    text = to_ics([CalendarEntry("a@quire", "Gita, a Bologna; sì\nbis", date(2026, 11, 4), all_day=True),
                   CalendarEntry("b@quire", "Lezione", date(2026, 11, 4), 480, 540, False, "x" * 200, "B12")],
                  "Quire", datetime(2026, 11, 4, 9, 0))
    assert "SUMMARY:Gita\\, a Bologna\; sì\\nbis\r\n" in text
    assert "DTSTART;VALUE=DATE:20261104\r\nDTEND;VALUE=DATE:20261105\r\n" in text
    assert "DTSTART:20261104T080000\r\nDTEND:20261104T090000\r\nDESCRIPTION:" in text and "LOCATION:B12" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n")) and "\r\n x" in text  # folded

    system = EvolutionCalendar(tmp_path / "data", tmp_path / "sources")
    services, _db = build_services(tmp_path / "q.db", register=FakeRegister(), credentials=MemoryCredentialStore(),
                                   calendar=system)
    today = services.planner.today()
    services.planner.save_event(None, EventInput(today, 0, 0, "Festa", all_day=True))
    services.planner.save_event(None, EventInput(today, 600, 660, "Dentista", "", "#000000"))
    services.calendar.publish()
    assert not system.file.exists() and not list((tmp_path).glob("sources/*"))  # off by default: nothing written
    services.calendar.set_enabled(True)
    first = system.file.read_bytes().decode()
    assert "SUMMARY:Festa" in first and "SUMMARY:Dentista" in first and system.file.stat().st_mode & 0o077 == 0
    source = (tmp_path / "sources" / system.SOURCE).read_text()
    assert f"CustomFile=file://{system.file}" in source and "BackendName=local" in source and "Writable=false" in source
    before = system.file.stat().st_mtime_ns
    services.calendar.publish()
    assert system.file.stat().st_mtime_ns == before  # unchanged: not rewritten, so nothing reloads
    assert "\r\n" in first
    uids = {line for line in first.split("\r\n") if line.startswith("UID:")}
    services.calendar.publish()
    assert len(uids) >= 2
    services.calendar.set_enabled(False)
    assert not (tmp_path / "sources" / system.SOURCE).exists()
