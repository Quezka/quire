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

    dialog = RoutineDialog(services, rid)
    assert dialog.title.text() == "Wake up" and [box.isChecked() for box in dialog.days][:5] == [True] * 5
    dialog.show()
    milestone = EventDialog(services, day=TODAY, milestone=True)
    milestone.show()
    assert milestone.milestone.isChecked() and not milestone.end.isVisible()
    milestone.milestone.setChecked(False)
    assert milestone.end.isVisible()
    for d in (dialog, milestone):
        d.close()

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
