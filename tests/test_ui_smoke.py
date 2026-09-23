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
    CourseDialog, CoursesDialog, EventDialog, TaskDialog,
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
                   TaskDialog(services, task_id, parent=window), TaskDialog(services, parent=window)]:
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
