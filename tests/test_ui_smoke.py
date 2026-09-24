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
    # Actually destroy it, so its pages stop listening to app-wide signals.
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


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
    assert [page.subjects.item(i).text() for i in range(page.subjects.count())] == ["Fisica"]
    assert page.tile_average.value.text() == "8.00"
    topics = [page.lessons.item(i).text() for i in range(page.lessons.count())]
    assert topics == ["Today", "Moto rettilineo"]  # grouped under a day heading
    assert not window.grab().isNull()

    # Clicking a subject shows its grades underneath.
    page._subject_clicked(page.subjects.item(0))
    assert page.subjects.count() == 2
    page._subject_clicked(page.subjects.item(0))
    assert page.subjects.count() == 1

    # Double-clicking a lesson topic opens that lesson's class notes.
    lesson = page.lessons.item(1)
    page._open_lesson_note(lesson)
    assert window.stack.currentWidget() is window.notes
    assert window.notes.note.title.startswith("Fisica")


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
    from quire.application.inputs import CourseInput, SlotInput

    register.subjects_ = [RemoteSubject("7", "MATEMATICA", ("ROSSI MARIO",))]
    services.school_sync.connect("S1", "secret")
    services.school_sync.sync()
    mine = services.timetable.save_course(
        None, CourseInput("Maths", slots=(SlotInput(0, 480, 540),)))

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

    from quire.application.inputs import JobInput

    from .conftest import TODAY

    page = window.work
    window.show_page(window.stack.indexOf(page))
    before = page.list.count()  # the demo data already has some shifts
    assert before and not page.empty.isVisible()

    job_id = services.work.save_job(None, JobInput("Café", "#f76b15", 10.0, 20.0))
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
    week.zoom.set_fit(False)  # scrolling only matters when the day doesn't fit
    week.zoom.level = 64.0
    week.zoom.apply()
    week.set_week(week.anchor)
    app.processEvents()  # runs the deferred scroll
    # The demo's late Saturday shift carries over to 00:00 on Sunday...
    assert any(b.start == 0 and b.carry_over for b in week.grid.blocks)
    # ...without stretching the shown hours back to midnight.
    assert week.grid.start_min >= 7 * 60
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

    from quire.application.inputs import JobInput

    from .conftest import TODAY

    job_id = services.work.save_job(None, JobInput("Library", "#12a594", 9.0))
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
    assert sorted(p.weekday for p in job.weekly) == [0, 1, 2, 3, 4, 5]

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

    from quire.application.inputs import JobInput, PatternInput
    from quire.presentation import dialogs

    from .conftest import TODAY

    job_id = services.work.save_job(None, JobInput("Cinema"),
                                    weekly=[PatternInput(4, 18 * 60, 22 * 60)])
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



def test_fit_day_shows_the_whole_day_without_scrolling(window, app):
    window.resize(1200, 780)
    for index, page in ((0, window.today), (1, window.week)):
        window.show_page(index)
        page.zoom.set_fit(True)
        app.processEvents()
        page.zoom.apply()
        app.processEvents()
        viewport = page.scroll.viewport().height()
        assert page.grid.minimumHeight() <= viewport + 1
        assert page.scroll.verticalScrollBar().maximum() == 0


def test_zoom_in_and_out_and_remembered(window, app):
    from PySide6.QtCore import QSettings

    window.show_page(0)
    zoom = window.today.zoom
    zoom.set_fit(True)
    app.processEvents()
    fitted = window.today.grid.hour_height
    zoom.zoom_in()
    assert not zoom.fit and window.today.grid.hour_height > fitted
    zoomed = window.today.grid.hour_height
    zoom.zoom_out()
    assert window.today.grid.hour_height < zoomed
    assert QSettings().value("zoom/today/fit", type=bool) is False
    assert abs(float(QSettings().value("zoom/today/hour")) - window.today.grid.hour_height) < 0.01


def test_ctrl_wheel_zooms_and_plain_wheel_scrolls(window, app):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    window.show_page(0)
    grid, zoom = window.today.grid, window.today.zoom
    zoom.set_fit(False)
    before = grid.hour_height

    def wheel(modifiers):
        event = QWheelEvent(QPointF(100, 200), QPointF(grid.mapToGlobal(QPoint(100, 200))),
                            QPoint(0, 0), QPoint(0, 120), Qt.NoButton, modifiers,
                            Qt.NoScrollPhase, False)
        app.sendEvent(grid, event)

    wheel(Qt.ControlModifier)
    assert grid.hour_height > before
    after_zoom = grid.hour_height
    wheel(Qt.NoModifier)
    assert grid.hour_height == after_zoom


def test_zoom_level_is_clamped(window):
    from quire.presentation.widgets import TimeGrid

    zoom = window.today.zoom
    for _ in range(30):
        zoom.zoom_in()
    assert window.today.grid.hour_height == TimeGrid.MAX_HOUR
    for _ in range(40):
        zoom.zoom_out()
    assert window.today.grid.hour_height == TimeGrid.MIN_HOUR



def test_school_term_switcher_filters_grades(window, services, register, app):
    from datetime import date

    from PySide6.QtCore import QThreadPool

    from quire.application.ports import RemoteGrade, RemoteSubject

    register.subjects_ = [RemoteSubject("1", "FISICA")]
    register.grades_ = [
        RemoteGrade("a", date(2026, 9, 10), "1", "FISICA", "4", 4.0, period="Trimestre"),
        RemoteGrade("b", date(2026, 9, 20), "1", "FISICA", "8", 8.0, period="Pentamestre"),
    ]
    page = window.school
    window.show_page(window.stack.indexOf(page))
    page.username.setText("S1")
    page.password.setText("secret")
    page._connect()
    QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    assert page.periods.isVisibleTo(page)
    assert [b.text() for b in page._period_buttons.buttons()] == [
        "All year", "Trimestre", "Pentamestre"]
    assert page.tile_average.value.text() == "6.00"
    assert page.tile_attention.value.text() == "0"
    page._pick_period("Trimestre")
    assert page.tile_average.value.text() == "4.00"
    assert page.tile_attention.value.text() == "1"


def test_school_agenda_lists_homework_and_ticks_it_off(window, services, register, app):
    from datetime import timedelta

    from PySide6.QtCore import QPoint, QThreadPool
    from PySide6.QtTest import QTest

    from quire.application.ports import RemoteAssignment, RemoteSubject
    from quire.application.types import TaskKind

    from .conftest import TODAY

    register.subjects_ = [RemoteSubject("4", "LINGUA STRANIERA INGLESE")]
    register.homework_ = [RemoteAssignment("141468", TODAY, TaskKind.HOMEWORK,
                                           "Workbook p. 18", "4", "LINGUA STRANIERA INGLESE",
                                           feed="homework")]
    register.assignments_ = [RemoteAssignment("9", TODAY - timedelta(days=5), TaskKind.TASK,
                                              "Portare il libro", "4", "LINGUA STRANIERA INGLESE")]
    page = window.school
    window.show_page(window.stack.indexOf(page))
    page.username.setText("S1")
    page.password.setText("secret")
    page._connect()
    QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()

    rows = [page.coming.item(i).text() for i in range(page.coming.count())]
    assert rows == ["Overdue", "Portare il libro", "Today", "Workbook p. 18"]

    # Click the round checkbox on the homework row.
    row = page.coming.item(3)
    rect = page.coming.visualItemRect(row)
    QTest.mouseClick(page.coming.viewport(), Qt.LeftButton,
                     pos=QPoint(rect.left() + 19, rect.top() + 19))
    app.processEvents()
    app.processEvents()
    homework = next(t for t in services.tasks.groups(include_done=True)
                    for t in t.items if t.task.title == "Workbook p. 18")
    assert homework.task.done
    assert "Workbook p. 18" not in [page.coming.item(i).text() for i in range(page.coming.count())]
    page.show_done.setChecked(True)
    assert "Workbook p. 18" in [page.coming.item(i).text() for i in range(page.coming.count())]



def test_focus_page_start_pause_and_sidebar_countdown(window, services, app):
    from quire.application.types import Phase

    page = window.focus
    window.show_page(window.stack.indexOf(page))
    button = window.sidebar.group.button(window.stack.indexOf(page))
    assert page.start_btn.text() == "Start" and button.text() == "  Focus"

    page._toggle()
    assert page.start_btn.text() == "Pause"
    assert button.text().startswith("  Focus   2")  # e.g. "  Focus   25:00"
    assert window.windowTitle().endswith("· Quire")

    page._toggle()
    assert page.start_btn.text() == "Resume" and button.text() == "  Focus"
    assert window.windowTitle() == "Quire"

    page._skip()
    assert services.focus.state().phase is Phase.SHORT_BREAK
    page._reset()
    assert services.focus.state().phase is Phase.WORK and page.start_btn.text() == "Start"
    assert not window.grab().isNull()


def test_focus_redraws_do_not_pile_up_theme_listeners(window, app):
    from quire.presentation import theme

    page = window.focus
    page._toggle()
    before = theme.manager().receivers("2changed(PyObject)")
    for _ in range(50):
        page._tick()
    assert theme.manager().receivers("2changed(PyObject)") == before
    page._toggle()


def test_settings_currency_changes_the_work_page(window, services, app):
    from quire.application.inputs import JobInput, ShiftInput
    from quire.presentation.formatting import money
    from quire.presentation.preferences import preferences
    from quire.presentation.settings import SettingsDialog

    from .conftest import TODAY

    job_id = services.work.save_job(None, JobInput("Café", hourly_rate=10.0))
    services.work.save_shift(None, ShiftInput(job_id, TODAY, 18 * 60, 20 * 60))
    dialog = SettingsDialog(services, lambda: None, window)
    dialog.currency.setCurrentIndex(dialog.currency.findData("EUR"))
    assert preferences().currency() == "EUR"
    assert "€" in money(8.5) and "€" in dialog.sample.text()
    assert "€" in window.work.week.detail.text()

    dialog.appearance.setCurrentIndex(dialog.appearance.findData("dark"))
    from quire.presentation import theme
    assert theme.current().dark
    dialog.currency.setCurrentIndex(0)  # back to the system default
    assert preferences().currency() == ""


def test_everything_renders_in_russian(app, services, register):
    """Build every page and dialog in Russian: catches bad placeholders at runtime."""
    from quire.presentation import i18n
    from quire.presentation.formatting import long_date, plural, relative_date
    from quire.presentation.settings import SettingsDialog

    from .conftest import TODAY

    i18n.install("ru", app)
    try:
        seed(services)
        w = MainWindow(services)
        w.show()
        for index in range(w.stack.count()):
            w.show_page(index)
            app.processEvents()
            assert not w.grab().isNull()
        assert w.today.title.text() == "Среда, 23 сентября"
        assert w.week.title.text() == "Сентябрь 2026"
        assert w.focus.start_btn.text() == "Начать"
        assert relative_date(TODAY, TODAY) == "Сегодня"
        assert plural(3, "class", "es") == "3 урока" and plural(5, "class", "es") == "5 уроков"
        assert long_date(TODAY).startswith("Среда")
        task_id = services.tasks.groups()[0].items[0].task.id
        for dialog in [CourseDialog(services, services.timetable.courses()[0].id, w),
                       TaskDialog(services, task_id, parent=w), EventDialog(services, parent=w),
                       JobDialog(services, parent=w), JobsDialog(services, w),
                       ShiftDialog(services, parent=w), SettingsDialog(services, lambda: None, w)]:
            dialog.show()
            dialog.reject()
        w.close()
        w.deleteLater()
    finally:
        i18n.install("en", app)


def test_task_view_checks_and_edits_without_losing_the_sync_link(window, services, app):
    from quire.application.inputs import TaskInput
    from quire.presentation.task_view import TaskView

    from .conftest import TODAY

    task_id = services.tasks.save(None, TaskInput("Esercizi pag. 34", due=TODAY,
                                                  details="1-5 e 8"))
    stored = services.tasks._tasks.get(task_id)  # as if the sync had imported it
    stored.external_id = "classeviva:homework:77"
    services.tasks._tasks.update(stored)
    view = TaskView(services, task_id, window)
    view.show()
    assert view.title.text() == "Esercizi pag. 34"
    assert view.done_btn.text() == "Mark as done" and view.source.isVisibleTo(view)
    assert view.body.toPlainText() == "1-5 e 8"

    view._toggle_done()
    assert services.tasks.task(task_id).done and view.done_btn.text() == "Mark as not done"
    view._toggle_done()
    assert not services.tasks.task(task_id).done

    # Editing an imported task keeps its link to Classeviva (no duplicate at next sync).
    editor = TaskDialog(services, task_id, parent=view)
    editor.title.setText("Esercizi pag. 34-35")
    editor._save()
    saved = services.tasks.task(task_id)
    assert saved.title == "Esercizi pag. 34-35"
    assert services.tasks._tasks.get(task_id).external_id == "classeviva:homework:77"
    view.refresh()
    assert view.title.text() == "Esercizi pag. 34-35"
    view.reject()  # closing works: nothing shadows QDialog.done()


def test_task_editor_quick_due_dates(window, services):
    from datetime import timedelta

    from .conftest import TODAY

    maths = next(c for c in services.timetable.courses() if c.name == "Mathematics")
    editor = TaskDialog(services, parent=window)
    assert not editor.next_class.isEnabled()  # no course picked yet
    editor.course.setCurrentIndex(editor.course.findData(maths.id))
    assert editor.next_class.isEnabled()
    editor.next_class.click()
    assert editor.has_due.isChecked()
    assert editor.due.date().toPython() == services.timetable.next_meeting(maths.id, TODAY)
    editor.findChildren(type(editor.next_class))[1].click()  # "Tomorrow"
    assert editor.due.date().toPython() == TODAY + timedelta(days=1)
    editor.reject()


def test_today_lists_everything_to_do_grouped_by_day(window, services, app):
    from datetime import timedelta

    from quire.application.inputs import TaskInput
    from quire.presentation.widgets import TwoLineDelegate

    from .conftest import TODAY

    services.tasks.save(None, TaskInput("Far away essay", due=TODAY + timedelta(days=30)))
    services.tasks.save(None, TaskInput("Next week reading", due=TODAY + timedelta(days=6)))
    window.show_page(0)
    window.today.set_day(TODAY)
    rows = [window.today.tasks.item(i) for i in range(window.today.tasks.count())]
    headings = [r.text() for r in rows if r.data(TwoLineDelegate.HEADER)]
    titles = [r.text() for r in rows if not r.data(TwoLineDelegate.HEADER)]
    assert headings[:2] == ["Overdue", "Today"] and "Tomorrow" in headings
    assert "Next week reading" in titles and "Far away essay" not in titles  # 14-day window

    window.today.set_day(TODAY + timedelta(days=1))  # another day: just that day
    rows = [window.today.tasks.item(i) for i in range(window.today.tasks.count())]
    assert not any(r.data(TwoLineDelegate.HEADER) for r in rows)


def test_saving_a_new_task_from_the_editor(window, services):
    """Regression: Qt returned the Type as a plain string and saving crashed."""
    from quire.application.types import TaskKind

    editor = TaskDialog(services, parent=window)
    editor.title.setText("Revise for the history test")
    editor.kind.setCurrentIndex(editor.kind.findData(TaskKind.EXAM))
    editor._save()
    saved = next(i.task for g in services.tasks.groups(include_done=True) for i in g.items
                 if i.task.title == "Revise for the history test")
    assert saved.kind is TaskKind.EXAM


def test_reminder_settings_and_notification_text(window, services, monkeypatch):
    from datetime import datetime

    from quire.application.dto import AgendaItem, ItemKind
    from quire.application.records import TimeSpan
    from quire.application.services import Reminder
    from quire.presentation import reminders
    from quire.presentation.settings import SettingsDialog

    from .conftest import TODAY

    dialog = SettingsDialog(services, lambda: None, window)
    dialog.remind.setCurrentIndex(dialog.remind.findData(15))
    dialog.remind_classes.setChecked(True)
    saved = services.reminders.settings()
    assert (saved.minutes_before, saved.classes, saved.events) == (15, True, True)
    dialog.remind.setCurrentIndex(dialog.remind.findData(None))
    assert services.reminders.settings().minutes_before is None
    assert not dialog.remind_events.isEnabled()

    item = AgendaItem(ItemKind.EVENT, 1, TODAY, TimeSpan(14 * 60, 15 * 60), "Dentist", "#fff",
                      room="Via Roma 3", details="Bring the card\nsecond line")
    shown = []
    monkeypatch.setattr(reminders, "notify", lambda title, body: shown.append((title, body)))
    monkeypatch.setattr(services.reminders, "due", lambda: [
        Reminder(item, datetime(2026, 9, 23, 14, 0), 10)])
    window.reminders.check()
    assert shown == [("Dentist in 10 min", "Event · 14:00–15:00 · Via Roma 3\nBring the card")]
