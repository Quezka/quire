from datetime import datetime, timedelta

import pytest

from quire.application.errors import ValidationError
from quire.application.inputs import SleepInput
from quire.domain import FocusSession, regularity, should_wind_down, sleep_stats
from quire.domain.sleep import SleepLog

from .conftest import TODAY
from .test_quiet import MovableClock, make


def at(hour, minute=0, days=0):
    return datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute) + timedelta(days=days)


def test_regularity_streak_and_wind_down_rules():
    steady = [SleepLog(TODAY - timedelta(days=i), 23 * 60 + (10 if i % 2 else 0), 7 * 60) for i in range(5)]
    assert regularity(sleep_stats(steady, 8).bedtime_spread) == "steady"
    wandering = [SleepLog(TODAY - timedelta(days=i), (21 + 2 * (i % 3)) * 60, 7 * 60) for i in range(6)]
    assert regularity(sleep_stats(wandering, 8).bedtime_spread) == "irregular"

    nights = [SleepLog(TODAY - timedelta(days=i), 22 * 60 + 30, 7 * 60) for i in range(4)]
    assert sleep_stats(nights, 8).streak == 4
    nights[2] = SleepLog(TODAY - timedelta(days=2), 3 * 60, 7 * 60)  # a 4 h night breaks it
    assert sleep_stats(nights, 8).streak == 2
    assert sleep_stats([nights[0], nights[3]], 8).streak == 1  # a gap in the days breaks it too

    assert should_wind_down(21 * 60 + 45, 22 * 60) and not should_wind_down(20 * 60, 22 * 60)
    assert not should_wind_down(22 * 60, 22 * 60) and not should_wind_down(23 * 60, 22 * 60)
    assert should_wind_down(23 * 60 + 40, 0)  # bedtime at midnight


def test_one_tap_logging_closes_the_night_you_started():
    services, clock, quiet, db = make()
    sleep = services.sleep
    with pytest.raises(ValidationError):
        sleep.wake_up()  # nothing started
    clock.at = at(23, 15, days=-1)
    sleep.go_to_sleep()
    assert sleep.overview().asleep_since == 23 * 60 + 15
    clock.at = at(6, 50)
    night = sleep.wake_up()
    assert (night.day, night.asleep, night.woke, night.minutes) == (TODAY, 23 * 60 + 15, 6 * 60 + 50, 7 * 60 + 35)
    assert sleep.overview().asleep_since is None and sleep.night(TODAY).minutes == 455

    clock.at = at(22)
    sleep.go_to_sleep()
    clock.at = at(22, 10, days=1)  # a forgotten start, a day later
    with pytest.raises(ValidationError):
        sleep.wake_up()
    sleep.cancel_going_to_sleep()
    assert sleep.overview().asleep_since is None
    db.close()


def test_wind_down_reminder_comes_once_a_day_and_not_while_asleep():
    services, clock, quiet, db = make()
    sleep = services.sleep
    sleep.save_goal(8, 6 * 60)  # bed by 22:00
    clock.at = at(20)
    assert sleep.reminder() is None
    clock.at = at(21, 40)
    assert sleep.reminder() == 22 * 60
    assert sleep.reminder() is None  # only once
    sleep.set_remind(False)
    clock.at = at(21, 40, days=1)
    assert sleep.reminder() is None  # switched off
    sleep.set_remind(True)
    sleep.go_to_sleep()
    assert sleep.reminder() is None  # already in bed
    db.close()


def test_overview_compares_weeks_and_focus_after_full_and_short_nights():
    services, clock, quiet, db = make()
    sleep = services.sleep
    focus = services.focus
    for i in range(0, 7):  # this week: 8 h
        sleep.save(SleepInput(TODAY - timedelta(days=i), 23 * 60, 7 * 60))
    for i in range(7, 12):  # the week before: 6 h
        sleep.save(SleepInput(TODAY - timedelta(days=i), 1 * 60, 7 * 60))
    o = sleep.overview()
    assert o.last_week_average == 360 and o.average_minutes > 360 and o.streak == 7
    assert o.focus_after_enough is None  # no focus data yet
    log = focus._log  # the repository behind the service
    for i in range(0, 7):
        log.add(FocusSession(datetime.combine(TODAY - timedelta(days=i), datetime.min.time()).replace(hour=10), 50))
    for i in range(7, 12):
        log.add(FocusSession(datetime.combine(TODAY - timedelta(days=i), datetime.min.time()).replace(hour=10), 20))
    o = sleep.overview()
    assert (o.focus_after_enough, o.focus_after_short) == (50, 20)
    db.close()
