from datetime import datetime, timedelta

import pytest

from quire.application.inputs import CourseInput, EventInput, RoutineInput, SlotInput
from quire.application.services import QuietSettings
from quire.application.services.quiet import merge_periods, status_at
from quire.bootstrap import build_services
from quire.infrastructure.credentials import MemoryCredentialStore

from .conftest import TODAY
from .fakes import FakeCloud, FakeDiagrams, FakeInstaller, FakeLoginItem, FakeQuiet, FakeRegister, FakeReleases


class MovableClock:
    def __init__(self, hour, minute=0):
        self.at = datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute)

    def today(self):
        return self.at.date()

    def now(self):
        return self.at


def make(hour=12, available=True):
    clock = MovableClock(hour)
    quiet = FakeQuiet(available)
    services, db = build_services(":memory:", clock, FakeRegister(), MemoryCredentialStore(), FakeCloud(),
                                  MemoryCredentialStore(), FakeReleases(), FakeInstaller(), FakeLoginItem(),
                                  FakeDiagrams(), quiet)
    return services, clock, quiet, db


def at(hour, minute=0, days=0):
    return datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute) + timedelta(days=days)


def test_touching_and_overlapping_periods_join():
    joined = merge_periods([(at(9), at(10)), (at(10), at(11)), (at(13), at(14)), (at(13, 30), at(15))])
    assert joined == [(at(9), at(11)), (at(13), at(15))]
    assert status_at(joined, at(10, 30)).until == at(11)
    after = status_at(joined, at(11, 30))
    assert not after.active and after.next_start == at(13)
    assert status_at([], at(8)).next_start is None


def test_it_does_nothing_until_it_is_switched_on():
    services, clock, quiet, db = make(10)
    services.planner.save_event(None, EventInput(TODAY, 9 * 60, 11 * 60, "Exam"))
    assert services.quiet.tick() is False and quiet.calls == []
    db.close()


def test_events_silence_while_they_last_and_it_undoes_only_its_own_change():
    services, clock, quiet, db = make(8)
    services.planner.save_event(None, EventInput(TODAY, 9 * 60, 11 * 60, "Exam"))
    services.quiet.save_settings(QuietSettings(enabled=True))
    assert not quiet.on  # 08:00, not yet
    assert services.quiet.status().next_start == at(9)

    clock.at = at(9, 30)
    assert services.quiet.tick() and quiet.on
    services.quiet.tick()
    assert quiet.calls == [True]  # not switched twice

    clock.at = at(11)
    assert not services.quiet.tick() and not quiet.on and quiet.calls == [True, False]
    services.quiet.tick()
    assert quiet.calls == [True, False]  # and nothing more to undo
    db.close()


def test_only_the_chosen_kinds_count_and_milestones_never_do():
    services, clock, quiet, db = make(10)
    services.planner.save_event(None, EventInput(TODAY, 9 * 60, 11 * 60, "Dentist"))
    services.planner.save_event(None, EventInput(TODAY, 10 * 60, 0, "Take meds", milestone=True))
    services.planner.save_routine(None, RoutineInput("Wake up", 10 * 60))
    services.timetable.save_course(None, CourseInput("Maths", slots=(SlotInput(TODAY.weekday(), 600, 660),)))
    services.quiet.save_settings(QuietSettings(enabled=True, classes=False, events=False))
    assert not services.quiet.tick()  # events and classes are off, shifts weren't asked for
    services.quiet.save_settings(QuietSettings(enabled=True, classes=True, events=False))
    assert services.quiet.tick()
    assert services.quiet.status().until == at(11)  # the class, not the dentist
    db.close()


def test_leaving_it_on_a_desktop_that_cannot_silence_does_nothing_and_release_restores():
    services, clock, quiet, db = make(10, available=False)
    services.planner.save_event(None, EventInput(TODAY, 9 * 60, 11 * 60, "Exam"))
    services.quiet.save_settings(QuietSettings(enabled=True))
    assert not services.quiet.tick() and quiet.calls == []
    db.close()

    services, clock, quiet, db = make(10)
    services.planner.save_event(None, EventInput(TODAY, 9 * 60, 11 * 60, "Exam"))
    services.quiet.save_settings(QuietSettings(enabled=True))
    assert quiet.on
    services.quiet.release()
    assert not quiet.on
    services.quiet.release()
    assert quiet.calls == [True, False]
    db.close()
