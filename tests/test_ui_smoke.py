"""Build the real UI offscreen and poke every page and dialog.

Catches crashes that only surface through Qt (signal wiring, shadowed Qt
methods, bad style sheets) without needing a display.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings, Qt  # noqa: E402

from quire.demo import seed  # noqa: E402
from quire.presentation import theme  # noqa: E402
from quire.presentation.dialogs import (  # noqa: E402
    CourseDialog, CoursesDialog, EventDialog, JobDialog, JobsDialog, ShiftDialog, TaskDialog,
)
from quire.presentation.main_window import MainWindow  # noqa: E402
from quire.presentation.qt_app import create_application  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or create_application(["quire-tests"])
    app.setOrganizationName("QuireTests")
    app.setApplicationName("QuireTests")
    QSettings().clear()
    return app


@pytest.fixture
def window(app, services):
    seed(services)
    w = MainWindow(services)
    w.show()
    yield w
    w.close()
    w.deleteLater()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_page_renders(window, app, mode):
    theme.manager().set_mode(mode)
    for index in range(window.stack.count()):
        window.show_page(index)
        app.processEvents()
        assert not window.grab().isNull()


def test_dialogs_open_and_cancel(window, services):
    task_id = services.tasks.groups()[0].items[0].task.id
    course_id = services.timetable.courses()[0].id
    for dialog in [CourseDialog(services, course_id, window), CourseDialog(services, None, window),
                   CoursesDialog(services, window), EventDialog(services, parent=window),
                   TaskDialog(services, task_id, parent=window), TaskDialog(services, parent=window),
                   JobDialog(services, parent=window), JobsDialog(services, window),
                   ShiftDialog(services, parent=window)]:
        dialog.show()
        dialog.reject()


def test_class_note_flow(window, services):
    course = services.timetable.courses()[0]
    window.open_class_note(course.id, services.planner.today())
    assert window.stack.currentWidget() is window.notes
    assert window.notes.note.title.startswith(course.name)


def test_school_page_connects_and_shows_synced_data(window, services, register, app):
    from quire.application.ports import RemoteGrade, RemoteLesson, RemoteSubject
    from .conftest import TODAY

    register.subjects_ = [RemoteSubject("1", "FISICA")]
    register.grades_ = [RemoteGrade("g", TODAY, "1", "FISICA", "8", 8.0)]
    register.lessons_ = [RemoteLesson("l", TODAY, "1", "FISICA", "Moto rettilineo")]
    page = window.school
    window.show_page(window.stack.indexOf(page))
    assert page.pages.currentIndex() == 0  # connect form

    page.username.setText("S1")
    page.password.setText("wrong")
    page._connect()
    assert "wrong" in page.connect_error.text()

    page.password.setText("secret")
    page._connect()  # starts a background sync
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    assert page.pages.currentIndex() == 1
    assert page.grades.topLevelItemCount() == 1
    assert page.lessons.item(0).text() == "Moto rettilineo"
    assert not window.grab().isNull()


def test_notes_group_by_topic(window, services, app):
    from quire.presentation.widgets import TwoLineDelegate

    notes = window.notes
    window.show_page(window.stack.indexOf(notes))
    bio = next(c for c in services.timetable.courses() if c.name == "Biology")
    notes.group_btn.setChecked(True)
    app.processEvents()

    rows = [notes.list.item(i) for i in range(notes.list.count())]
    headers = [(r.data(TwoLineDelegate.HEADER), r.text()) for r in rows
               if r.data(TwoLineDelegate.HEADER)]
    assert (1, "Biology") in headers and (2, "Cell biology") in headers
    assert (2, "Genetics") in headers

    # Collapsing a topic hides its notes but keeps the heading.
    topic_row = next(r for r in rows if r.text() == "Cell biology")
    before = notes.list.count()
    notes._header_clicked(topic_row)
    assert notes.list.count() == before - 2
    notes._header_clicked(next(notes.list.item(i) for i in range(notes.list.count())
                               if notes.list.item(i).text() == "Cell biology"))
    assert notes.list.count() == before

    # Filing the open note under a topic from the editor toolbar.
    rows = [notes.list.item(i) for i in range(notes.list.count())]  # the list was rebuilt
    first = next(r for r in rows if r.data(Qt.UserRole) is not None)
    notes.list.setCurrentItem(first)
    notes.course.setCurrentIndex(notes.course.findData(bio.id))
    notes.topic.setEditText("genetics")
    notes._topic_changed()
    assert notes.note.topic == "Genetics"  # adopted the existing spelling
    assert not window.grab().isNull()

    notes.group_btn.setChecked(False)
    assert not any(notes.list.item(i).data(TwoLineDelegate.HEADER)
                   for i in range(notes.list.count()))


def test_course_dialog_links_subject_and_keeps_link_on_save(window, services, register):
    from quire.application.ports import RemoteSubject
    from quire.domain import ClassSlot, Course, TimeRange

    register.subjects_ = [RemoteSubject("7", "MATEMATICA", ("ROSSI MARIO",))]
    services.school.connect("S1", "secret")
    services.school.sync()
    mine = services.timetable.save_course(
        Course("Maths", slots=[ClassSlot(0, TimeRange(480, 540))]))

    dialog = CourseDialog(services, mine, window)
    dialog.subject.setCurrentIndex(dialog.subject.findData("classeviva:subject:7"))
    dialog._save()
    assert services.timetable.course(mine).external_id == "classeviva:subject:7"
    assert "Matematica" not in [c.name for c in services.timetable.courses()]

    # Re-saving without touching the picker must not drop the link.
    again = CourseDialog(services, mine, window)
    again.room.setText("B12")
    again._save()
    saved = services.timetable.course(mine)
    assert saved.external_id == "classeviva:subject:7" and saved.room == "B12"


def test_work_page_and_shift_dialog(window, services, app):
    from datetime import timedelta

    from quire.domain import Job

    from .conftest import TODAY

    page = window.work
    window.show_page(window.stack.indexOf(page))
    before = page.list.count()  # the demo data already has some shifts
    assert before and not page.empty.isVisible()

    job_id = services.work.save_job(Job("Café", "#f76b15", 10.0, deductions=20.0))
    dialog = ShiftDialog(services, day=TODAY, start=18 * 60, parent=window)
    select = dialog.job.findData(job_id)
    dialog.job.setCurrentIndex(select)
    dialog.end.setTime(dialog.end.time().fromString("01:00", "HH:mm"))
    dialog.break_min.setValue(30)
    dialog.repeat.setCurrentIndex(ShiftDialog.REPEAT_WEEKLY)
    assert dialog.next_day.text() == "ends next day"
    assert "6 h 30 paid" in dialog.summary.text()
    assert "gross" in dialog.summary.text() and "net" in dialog.summary.text()
    assert "each Wed" in dialog.summary.text()
    dialog._save()
    mine = [i for i in services.work.shifts_between(TODAY, TODAY + timedelta(days=8))
            if i.shift.job_id == job_id]
    assert len(mine) == 2 and all(i.shift.recurring for i in mine)
    upcoming_cafe = [i for i in services.work.upcoming() if i.shift.job_id == job_id]
    assert len(upcoming_cafe) >= 4  # it keeps repeating every week
    assert page.list.count() == before + len(upcoming_cafe)

    # The demo's Chemistry class on Wednesdays 10:30-11:20 clashes with a morning shift.
    clash = ShiftDialog(services, day=TODAY, start=10 * 60, parent=window)
    assert clash.clash.isVisibleTo(clash) and "Chemistry" in clash.clash.text()
    clash.reject()

    window.show_page(0)
    app.processEvents()
    assert "work shift" in window.today.subtitle.text()
    assert not window.grab().isNull()


def test_week_view_opens_at_the_school_day_not_midnight(window, app):
    from quire.presentation.widgets import TimeGrid

    window.show_page(1)
    week = window.week
    week.set_week(week.anchor)
    app.processEvents()  # runs the deferred scroll
    # The demo's late Saturday shift puts a block at 00:00 on Sunday.
    assert any(b.start == 0 for b in week.grid.blocks)
    first_class = week.grid.first_daytime_start()
    assert first_class >= 6 * 60
    expected = int(week.grid.y_for(first_class - 30)) - TimeGrid.PAD
    assert week.scroll.verticalScrollBar().value() == min(
        expected, week.scroll.verticalScrollBar().maximum())


@pytest.mark.parametrize("typed, expected", [
    ("8.50", 8.5), ("8,50", 8.5), ("12", 12.0), (" 1.234,50 ", 1234.5), ("1,234.50", 1234.5),
    ("", None),
])
def test_amount_parsing_accepts_both_decimal_marks(typed, expected):
    from quire.presentation.widgets import parse_amount
    assert parse_amount(typed) == expected


@pytest.mark.parametrize("typed", ["abc", "-3", "8.5.0x"])
def test_amount_parsing_rejects_junk(typed):
    from quire.presentation.widgets import parse_amount
    with pytest.raises(ValueError):
        parse_amount(typed)


def click_and_type(widget, text, app):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    target = widget.lineEdit() if hasattr(widget, "lineEdit") and widget.lineEdit() else widget
    QTest.mouseClick(target, Qt.LeftButton, pos=QPoint(target.width() // 3, target.height() // 2))
    app.processEvents()  # the spin box selects its text on the next event loop turn
    QTest.keyClicks(target, text)


def test_typing_an_hourly_rate_into_the_job_dialog_saves_it(window, services, app):
    dialog = JobDialog(services, parent=window)
    dialog.show()
    dialog.name.setText("Bar Centrale")
    click_and_type(dialog.rate, "8,50", app)
    dialog._save()
    job = next(j for j in services.work.jobs() if j.name == "Bar Centrale")
    assert job.hourly_rate == 8.5

    again = JobDialog(services, job.id, window)
    assert again.rate.text() == "8.50"
    again.rate.setText("")
    again._save()
    assert services.work.job(job.id).hourly_rate is None


def test_typing_into_the_shift_break_box_works(window, services, app):
    dialog = ShiftDialog(services, parent=window)
    dialog.show()
    app.processEvents()
    assert dialog.break_min.text() == "No break"
    click_and_type(dialog.break_min, "30", app)
    dialog.break_min.interpretText()
    assert dialog.break_min.value() == 30


def test_repeat_every_work_day_from_the_shift_dialog(window, services, app):
    from datetime import timedelta

    from quire.domain import Job

    from .conftest import TODAY

    job_id = services.work.save_job(Job("Library", "#12a594", 9.0))
    dialog = ShiftDialog(services, day=TODAY, start=8 * 60, parent=window, job_id=job_id,
                         end=10 * 60)
    dialog.show()
    dialog.repeat.setCurrentIndex(ShiftDialog.REPEAT_WORKDAYS)
    dialog.has_until.setChecked(True)
    dialog.until.setDate(dialog.until.date().fromString("2026-10-02", "yyyy-MM-dd"))
    dialog._save()
    days = [i.shift.day.weekday() for i in services.work.shifts_between(
        TODAY, TODAY + timedelta(weeks=4)) if i.shift.job_id == job_id]
    assert days == [2, 3, 4, 0, 1, 2, 3, 4]  # Wed 23 Sep to Fri 2 Oct, weekdays only

    custom = ShiftDialog(services, day=TODAY, parent=window, job_id=job_id)
    custom.show()
    custom.repeat.setCurrentIndex(ShiftDialog.REPEAT_CUSTOM)
    assert custom.days.isVisibleTo(custom) and custom.days.days() == [2]


def test_job_dialog_weekly_schedule_and_tax_preset(window, services, app):
    from quire.presentation.dialogs import DEDUCTION_PRESETS

    dialog = JobDialog(services, parent=window)
    dialog.show()
    dialog.name.setText("Gelateria")
    dialog.rate.setText("9,50")
    dialog.preset.setCurrentIndex(1)  # occasional work, 20%
    assert dialog.deductions.text() == "20"
    dialog._add_row()  # defaults to Mon-Fri
    dialog._add_row([5], 15 * 60, 1 * 60, 30)  # Saturday late
    dialog._save()

    job = next(j for j in services.work.jobs() if j.name == "Gelateria")
    assert (job.hourly_rate, job.deductions) == (9.5, 20.0)
    schedule = job.active_schedule(services.planner.today())
    assert sorted(p.weekday for p in schedule) == [0, 1, 2, 3, 4, 5]

    again = JobDialog(services, job.id, window)
    assert again.table.rowCount() == 2
    assert again.table.cellWidget(0, 0).days() == [0, 1, 2, 3, 4]
    assert again.preset.currentText() == DEDUCTION_PRESETS[1][0]
    again.deductions.setText("12.5")
    again._deductions_typed()
    assert again.preset.currentText() == "Custom…"


def test_regular_shift_menu_skip_and_change(window, services, app, monkeypatch):
    from datetime import timedelta

    from PySide6.QtWidgets import QMenu

    from quire.domain import Job, ShiftPattern
    from quire.presentation import dialogs

    from .conftest import TODAY

    job_id = services.work.save_job(Job("Cinema"),
                                    weekly=[ShiftPattern.between(4, 18 * 60, 22 * 60)])
    friday = TODAY + timedelta(days=2)
    class ScriptedMenu(QMenu):
        choice = "Skip this week"

        def exec(self, *_args):
            return next(a for a in self.actions() if a.text() == self.choice)

    monkeypatch.setattr(dialogs, "QMenu", ScriptedMenu)
    dialogs.weekly_shift_menu(window, services, job_id, (friday, 18 * 60), None)
    days = [i.shift.day for i in services.work.shifts_between(friday, friday + timedelta(weeks=1))
            if i.shift.job_id == job_id]
    assert days == [friday + timedelta(weeks=1)]



def test_school_page_lists_parts_that_failed(window, services, register, app):
    from PySide6.QtCore import QThreadPool

    from quire.application.errors import RegisterError

    register.failing["grades"] = RegisterError("Classeviva's grades endpoint has moved")
    page = window.school
    window.show_page(window.stack.indexOf(page))
    page.username.setText("S1")
    page.password.setText("secret")
    page._connect()
    QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    texts = [page.news.item(i).text() for i in range(page.news.count())]
    assert any(t.startswith("Couldn't sync grades") for t in texts)
    assert "some parts failed" in page.subtitle.text()
