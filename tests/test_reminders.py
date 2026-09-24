from datetime import datetime, timedelta

import pytest

from quire.application.dto import ItemKind
from quire.application.inputs import (
    CourseInput, EventInput, JobInput, PatternInput, ShiftInput, SlotInput,
)
from quire.application.services import ReminderSettings
from quire.bootstrap import build_services
from quire.infrastructure.credentials import MemoryCredentialStore

from .conftest import TODAY
from .fakes import FakeRegister


class MovableClock:
    def __init__(self, now: datetime):
        self.moment = now

    def now(self):
        return self.moment

    def today(self):
        return self.moment.date()

    def set(self, hhmm: str, days: int = 0):
        h, m = map(int, hhmm.split(":"))
        self.moment = datetime.combine(TODAY + timedelta(days=days),
                                       datetime.min.time()).replace(hour=h, minute=m)


@pytest.fixture
def env(tmp_path):
    clock = MovableClock(datetime.combine(TODAY, datetime.min.time()).replace(hour=8))
    services, db = build_services(tmp_path / "r.db", clock, FakeRegister(),
                                  MemoryCredentialStore())
    yield services, clock
    db.close()


def test_reminds_once_shortly_before_an_event(env):
    services, clock = env
    services.planner.save_event(None, EventInput(TODAY, 14 * 60, 15 * 60, "Dentist"))
    clock.set("13:49")
    assert services.reminders.due() == []  # 11 minutes to go, reminders are at 10
    clock.set("13:50")
    (reminder,) = services.reminders.due()
    assert reminder.item.title == "Dentist" and reminder.minutes_left == 10
    clock.set("13:55")
    assert services.reminders.due() == []  # already announced


def test_late_starts_are_still_announced_but_old_ones_are_not(env):
    services, clock = env
    services.planner.save_event(None, EventInput(TODAY, 14 * 60, 15 * 60, "Dentist"))
    services.planner.save_event(None, EventInput(TODAY, 13 * 60, 15 * 60, "Long gone"))
    clock.set("14:01")  # the laptop just woke up
    assert [(r.item.title, r.minutes_left) for r in services.reminders.due()] == [("Dentist", 0)]


def test_classes_only_when_asked_and_shifts_by_default(env):
    services, clock = env
    services.timetable.save_course(None, CourseInput("Maths", slots=(
        SlotInput(TODAY.weekday(), 9 * 60, 10 * 60),)))
    job = services.work.save_job(None, JobInput("Pizzeria"))
    services.work.save_shift(None, ShiftInput(job, TODAY, 9 * 60 + 5, 12 * 60))
    clock.set("08:56")
    assert [r.item.kind for r in services.reminders.due()] == [ItemKind.SHIFT]

    services.reminders.save_settings(ReminderSettings(10, classes=True))
    services.reminders._sent.clear()
    assert [r.item.kind for r in services.reminders.due()] == [ItemKind.CLASS, ItemKind.SHIFT]


def test_overnight_weekly_shift_is_announced_once_at_its_start(env):
    services, clock = env
    services.work.save_job(None, JobInput("Bar"), weekly=[
        PatternInput(TODAY.weekday(), 23 * 60 + 30, 2 * 60)])
    clock.set("23:25")
    (reminder,) = services.reminders.due()
    assert reminder.starts == datetime.combine(TODAY, datetime.min.time()).replace(
        hour=23, minute=30)
    clock.set("00:00", days=1)
    assert services.reminders.due() == []  # the after-midnight part isn't a new start


def test_settings_round_trip_and_off(env):
    services, clock = env
    assert services.reminders.settings() == ReminderSettings()
    services.reminders.save_settings(ReminderSettings(None, events=True, classes=True,
                                                      shifts=False))
    assert services.reminders.settings() == ReminderSettings(None, True, True, False)
    services.planner.save_event(None, EventInput(TODAY, 8 * 60 + 5, 9 * 60, "Bus"))
    assert services.reminders.due() == []
