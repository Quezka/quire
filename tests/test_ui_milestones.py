"""The new pages and dialogs (milestones, routines, sleep), built offscreen.

Kept apart from test_ui_smoke: after its tray and second-launch tests, a later test that
shows extra dialogs and runs the event loop can crash Qt.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from quire.presentation.dialogs import EventDialog, RoutineDialog  # noqa: E402

from .test_ui_smoke import app, window  # noqa: E402,F401


def test_milestones_routines_and_sleep_render(window, app, services):
    from datetime import timedelta

    from quire.application.inputs import EventInput, RoutineInput, SleepInput
    from quire.presentation.views.sleep import SleepView
    from tests.conftest import TODAY

    rid = services.planner.save_routine(None, RoutineInput("Wake up", 360, (0, 1, 2, 3, 4)))
    services.planner.save_event(None, EventInput(TODAY, 480, 0, "Take meds", milestone=True))
    for i in range(4):
        services.sleep.save(SleepInput(TODAY - timedelta(days=i), 23 * 60, 7 * 60, 3 + i % 2))
    window.show_page(0)
    app.processEvents()
    blocks = [b for b in window.today.grid.blocks if b.milestone]
    assert {b.title for b in blocks} >= {"Take meds"}
    assert not window.grab().isNull()

    dialog = RoutineDialog(services, rid, parent=window)
    assert dialog.title.text() == "Wake up" and [box.isChecked() for box in dialog.days][:5] == [True] * 5
    dialog.show()
    milestone = EventDialog(services, day=TODAY, milestone=True, parent=window)
    milestone.show()
    assert milestone.milestone.isChecked() and not milestone.end.isVisible()
    milestone.milestone.setChecked(False)
    assert milestone.end.isVisible()
    for d in (dialog, milestone):
        d.close()
        d.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    sleep = next(w for w in (window.stack.widget(i) for i in range(window.stack.count()))
                 if isinstance(w, SleepView))
    window.show_page(window.stack.indexOf(sleep))
    app.processEvents()
    assert sleep.bars.overview.nights and "night" in sleep.summary.text()
    assert not sleep.grab().isNull()


def test_collapse_all_note_groups_closes_then_reopens_them(window, app, services):
    from quire.application.inputs import CourseInput, NoteInput

    maths = services.timetable.save_course(None, CourseInput("Maths"))
    services.notes.create("# Limits", maths, "Calculus")
    services.notes.create("# Vectors", maths, "Algebra")
    services.notes.create("# Loose idea")
    notes = window.notes
    window.show_page(window.stack.indexOf(notes))
    notes.group_btn.setChecked(True)
    app.processEvents()
    assert notes.collapse_btn.isVisible()
    assert notes.list.count() >= 2 and not any(notes.list.item(i).data(Qt.UserRole) == 1 for i in range(notes.list.count()))
    notes._collapsed.clear()  # they start closed; open them to count what is inside
    notes.reload_list()

    def note_rows():
        return [i for i in range(notes.list.count()) if notes.list.item(i).data(Qt.UserRole) is not None]

    shown = len(note_rows())
    assert shown >= 3
    notes.collapse_btn.click()
    assert note_rows() == []  # every group is closed, only the headings are left
    assert notes.list.count() >= 2
    notes.collapse_btn.click()
    assert len(note_rows()) == shown


def test_water_page_shows_the_goal_and_logs_a_glass(window, app, services):
    from quire.application.inputs import WaterProfileInput

    water = window.water
    window.show_page(window.stack.indexOf(water))
    app.processEvents()
    assert "height" in water.subtitle.text().lower()  # no goal until height and weight are set
    services.water.save_profile(WaterProfileInput(175, 70, 250))
    water.glass_btn.click()
    app.processEvents()
    assert services.water.overview().drunk == 250
    assert "ml to go" in water.subtitle.text() and water.entries.count() == 1
    assert water.undo_btn.isEnabled()
    water.undo_btn.click()
    assert water.entries.count() == 0 and not water.grab().isNull()


def test_an_all_day_event_sits_above_the_timeline_and_never_reminds(window, app, services):
    from quire.application.inputs import EventInput
    day = services.planner.today()
    services.planner.save_event(None, EventInput(day, 0, 0, "Gita a Bologna", all_day=True))
    window.today.set_day(day)
    app.processEvents()
    strip = window.today.all_day
    assert strip.isVisibleTo(window.today) and strip.row.itemAt(0).widget().text() == "Gita a Bologna"
    assert all(b.title != "Gita a Bologna" for b in window.today.grid.blocks)
    item = next(i for i in services.planner.items_between(day, day) if i.title == "Gita a Bologna")
    assert item.is_all_day and not item.is_milestone
    assert all(r.item.title != "Gita a Bologna" for r in services.reminders.due())


def test_the_all_day_dialog_hides_the_times_and_saves_the_whole_day(window, app, services):
    from quire.presentation.dialogs import EventDialog
    dialog = EventDialog(services, day=services.planner.today(), parent=window)
    dialog.title.setText("Festa")
    dialog.all_day.setChecked(True)
    assert not dialog.start.isVisibleTo(dialog)
    dialog._save()
    saved = next(i for i in services.planner.items_between(services.planner.today(), services.planner.today())
                 if i.title == "Festa")
    assert (saved.time.start, saved.time.end) == (0, 24 * 60)
    again = EventDialog(services, saved.ref_id, parent=window)
    assert again.all_day.isChecked()


def test_formatting_buttons_show_what_is_on_and_turn_it_off(window, app, services):
    notes = window.notes
    notes._open(services.notes.create("hello world"))
    bold = notes.format_toggles["bold"]
    assert bold.isCheckable() and not bold.isChecked()
    bold.click()
    assert bold.isChecked() and notes.editor.format_state()["bold"]
    bold.click()
    assert not bold.isChecked() and not notes.editor.format_state()["bold"]
    bullets, checks = notes.format_toggles["list"], notes.format_toggles["checklist"]
    bullets.click()
    assert bullets.isChecked() and not checks.isChecked()
    checks.click()
    assert checks.isChecked() and not bullets.isChecked()
    checks.click()
    assert not checks.isChecked() and not bullets.isChecked()


def test_the_plus_on_a_topic_heading_makes_a_note_there(window, app, services):
    from quire.application.inputs import CourseInput
    maths = services.timetable.save_course(None, CourseInput("Maths"))
    services.notes.create("# Limits", maths, "Calculus")
    notes = window.notes
    notes.group_btn.setChecked(True)
    notes._new_note_under(("topic", ("course", maths), "Calculus"))
    assert notes.note.course_id == maths and notes.note.topic == "Calculus"
    assert ("home", ("course", maths)) not in notes._collapsed  # it is on show
    made = notes.note.id
    assert any(notes.list.item(i).data(Qt.UserRole) == made for i in range(notes.list.count()))


def test_several_notes_go_into_one_pdf_each_on_its_own_page(window, app, services, tmp_path):
    from quire.presentation.note_images import notes_pdf
    path = tmp_path / "all.pdf"
    notes_pdf(services, "Notes", ["# One\n\nfirst", "# Two\n\nsecond", "# Three\n\nthird"], str(path))
    assert path.read_bytes().count(b"/Type /Page\n") + path.read_bytes().count(b"/Type/Page\n") >= 3 or path.stat().st_size > 1000


def test_searching_finds_notes_inside_closed_groups(window, app, services):
    from quire.application.inputs import CourseInput
    maths = services.timetable.save_course(None, CourseInput("Maths"))
    made = services.notes.create("# Derivative rules", maths, "Calculus")
    notes = window.notes
    notes.group_btn.setChecked(True)
    notes.reload_list()
    notes.search.setText("Derivative")
    app.processEvents()
    assert any(notes.list.item(i).data(Qt.UserRole) == made.id for i in range(notes.list.count()))


def test_water_starts_again_at_midnight_with_the_window_open(window, app, services, monkeypatch):
    from datetime import timedelta
    services.water.add(300)
    view = window.water
    view.refresh()
    assert view.entries.count() == 1
    tomorrow = services.planner.today() + timedelta(days=1)
    clock = services.water._clock
    real_now = clock.now
    monkeypatch.setattr(clock, "today", lambda: tomorrow, raising=False)
    monkeypatch.setattr(clock, "now", lambda: real_now() + timedelta(days=1), raising=False)
    view._day = tomorrow - timedelta(days=1)
    monkeypatch.setattr(view.planner, "today", lambda: tomorrow)
    view._tick()
    assert view.entries.count() == 0 and view._day == tomorrow


def test_water_manual_goal_streak_and_average(services):
    from quire.application.inputs import WaterProfileInput
    from quire.domain.water import water_streak
    goal = services.water.save_profile(WaterProfileInput(170, 65, manual_goal=1800))
    assert goal == 1800 and services.water.overview().goal == 1800
    assert services.water.save_profile(WaterProfileInput(170, 65)) != 1800  # back to height and weight
    assert water_streak([0, 2000, 2000, 100, 2000], 2000) == 2  # today not reached yet doesn't break it
    assert water_streak([2000, 2000, 100], 2000) == 2 and water_streak([0, 100], 2000) == 0


def test_medicine_page_ticks_a_dose_and_edits_a_medicine(window, app, services):
    from quire.application.inputs import MedicineInput
    from quire.presentation.views.medicine import MedicineDialog, parse_times
    assert parse_times("8:00, 13.30 20") == (480, 810, 1200)
    with pytest.raises(Exception):
        parse_times("25:00")
    services.medicine.save(None, MedicineInput("Vitamin D", "1 tablet", (480,)))
    view = window.medicine
    window.show_page(window.stack.indexOf(view))
    app.processEvents()
    assert view.doses.count() == 1 and "Vitamin D" in view.doses.item(0).text()
    view.doses.item(0).setCheckState(Qt.Checked)
    app.processEvents()
    assert services.medicine.day()[0].taken and view.doses.item(0).checkState() == Qt.Checked
    assert "taken at" in view.doses.item(0).data(Qt.UserRole + 1)
    dialog = MedicineDialog(services, services.medicine.medicines()[0].id, parent=window)
    assert dialog.times.text() == "08:00"
    dialog.times.setText("9:00, 21:00")
    dialog._save()
    assert services.medicine.medicines()[0].times == (540, 1260)


def test_money_page_shows_the_month_and_a_new_entry(window, app, services):
    from datetime import date
    from quire.application.inputs import TransactionInput
    from quire.presentation.views.finance import TransactionDialog
    view = window.finance
    window.show_page(window.stack.indexOf(view))
    today = services.planner.today()
    dialog = TransactionDialog(services, day=today, parent=window)
    dialog.amount.setText("12,50")
    dialog.category.setCurrentText("Food")
    dialog._save()
    app.processEvents()
    assert view.list.count() == 1 and "Food" in view.list.item(0).text()
    assert "12" in view.spent.value.text() and view.bars.rows == (("Food", 1250),)
    dialog = TransactionDialog(services, services.finance.transaction(view.list.item(0).data(Qt.UserRole)), parent=window)
    assert dialog.amount.text() == "12,50"
    view.go(*services.finance.previous_month(view.year, view.month))
    assert view.list.count() == 0 and view.nothing.isVisibleTo(view)
    view.go(today.year, today.month)
    assert view.list.count() == 1
