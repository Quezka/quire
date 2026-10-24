"""The new pages and dialogs (milestones, routines, sleep), built offscreen.

Kept apart from test_ui_smoke: after its tray and second-launch tests, a later test that
shows extra dialogs and runs the event loop can crash Qt.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

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
