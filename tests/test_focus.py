from datetime import datetime, timedelta

import pytest

from quire.domain import FocusSettings, Phase, PomodoroTimer, ValidationError

T0 = datetime(2026, 9, 24, 15, 0)


def minutes(n):
    return timedelta(minutes=n)


def test_counts_down_against_the_clock_and_pauses():
    timer = PomodoroTimer()
    assert not timer.running and timer.remaining(T0) == minutes(25)
    timer.start(T0)
    assert timer.remaining(T0 + minutes(10)) == minutes(15)
    assert timer.progress(T0 + minutes(10)) == pytest.approx(0.4)
    timer.pause(T0 + minutes(10))
    assert timer.remaining(T0 + minutes(40)) == minutes(15)  # paused: time stands still
    timer.start(T0 + minutes(40))
    assert timer.remaining(T0 + minutes(45)) == minutes(10)


def test_cycle_goes_work_break_and_long_break_after_the_last_round():
    timer = PomodoroTimer(FocusSettings(rounds=2))
    now = T0
    timer.start(now)
    phases = []
    for _ in range(4):
        now += timer.remaining(now)
        event = timer.tick(now)
        phases.append((event.phase, event.next_phase))
    assert phases == [
        (Phase.WORK, Phase.SHORT_BREAK),
        (Phase.SHORT_BREAK, Phase.WORK),
        (Phase.WORK, Phase.LONG_BREAK),
        (Phase.LONG_BREAK, Phase.WORK),
    ]
    assert timer.phase is Phase.WORK and timer.completed == 0 and timer.round == 1


def test_phase_end_reports_when_it_started_and_how_long_it_was():
    timer = PomodoroTimer()
    timer.start(T0)
    timer.pause(T0 + minutes(5))
    timer.start(T0 + minutes(10))
    event = timer.tick(T0 + minutes(30))
    assert event.started == T0 and event.minutes == 25


def test_no_auto_continue_waits_for_you():
    timer = PomodoroTimer(FocusSettings(auto_continue=False))
    timer.start(T0)
    timer.tick(T0 + minutes(25))
    assert timer.phase is Phase.SHORT_BREAK and not timer.running
    assert timer.remaining(T0 + minutes(60)) == minutes(5)


def test_auto_continue_runs_the_break_from_the_moment_focus_ended():
    timer = PomodoroTimer()
    timer.start(T0)
    timer.tick(T0 + minutes(25, ) + timedelta(seconds=3))  # noticed a bit late
    assert timer.running and timer.remaining(T0 + minutes(26)) == minutes(4)


def test_skip_does_not_count_the_round():
    timer = PomodoroTimer()
    timer.start(T0)
    timer.skip(T0 + minutes(3))
    assert timer.phase is Phase.SHORT_BREAK and timer.completed == 0 and timer.running
    timer.skip(T0 + minutes(4))
    assert timer.phase is Phase.WORK


def test_reset_starts_the_cycle_over():
    timer = PomodoroTimer()
    timer.start(T0)
    timer.tick(T0 + minutes(25))
    timer.reset()
    assert (timer.phase, timer.completed, timer.running) == (Phase.WORK, 0, False)
    assert timer.remaining(T0) == minutes(25)


def test_cutting_a_focus_session_short_counts_the_time_actually_spent():
    timer = PomodoroTimer(FocusSettings(work_minutes=25))
    assert timer.cut_short(T0) is None  # not started
    timer.start(T0)
    timer.pause(T0 + minutes(10))
    timer.start(T0 + minutes(40))  # the half hour paused doesn't count
    session = timer.cut_short(T0 + minutes(42) + timedelta(seconds=40))
    assert (session.started, session.minutes, session.complete) == (T0, 13, False)


def test_less_than_a_minute_or_a_break_leaves_nothing_to_log():
    timer = PomodoroTimer(FocusSettings(work_minutes=25))
    timer.start(T0)
    assert timer.cut_short(T0 + timedelta(seconds=25)) is None
    timer.skip(T0 + minutes(1))
    assert timer.phase is Phase.SHORT_BREAK
    assert timer.cut_short(T0 + minutes(3)) is None


def test_a_running_phase_keeps_its_length_when_settings_change():
    timer = PomodoroTimer(FocusSettings(work_minutes=25))
    timer.start(T0)
    timer.apply_settings(FocusSettings(work_minutes=50))
    assert timer.cut_short(T0 + minutes(20)).minutes == 20
    assert timer.tick(T0 + minutes(25)).minutes == 25


def test_new_settings_apply_to_a_fresh_timer_right_away():
    timer = PomodoroTimer()
    timer.apply_settings(FocusSettings(work_minutes=50))
    assert timer.remaining(T0) == minutes(50)
    timer.start(T0)
    timer.apply_settings(FocusSettings(work_minutes=30))  # mid-session: next phase
    assert timer.remaining(T0) == minutes(50)


@pytest.mark.parametrize("settings", [
    FocusSettings(work_minutes=0), FocusSettings(short_break_minutes=61),
    FocusSettings(long_break_minutes=0), FocusSettings(rounds=0), FocusSettings(rounds=13),
])
def test_settings_are_validated(settings):
    with pytest.raises(ValidationError):
        settings.validate()


# ---- FocusService ---------------------------------------------------------------

from quire.application.bus import Topic  # noqa: E402
from quire.bootstrap import build_services  # noqa: E402
from quire.application.inputs import TaskInput  # noqa: E402
from quire.application.records import FocusSettingsData  # noqa: E402
from quire.infrastructure.credentials import MemoryCredentialStore  # noqa: E402

from .fakes import FakeRegister  # noqa: E402


class MovableClock:
    def __init__(self, now: datetime):
        self.moment = now

    def now(self):
        return self.moment

    def today(self):
        return self.moment.date()

    def advance(self, **delta):
        self.moment += timedelta(**delta)


@pytest.fixture
def focus_env(tmp_path):
    clock = MovableClock(T0)
    path = tmp_path / "focus.db"
    services, db = build_services(path, clock, FakeRegister(), MemoryCredentialStore())
    yield services, clock, path
    db.close()


def test_finished_focus_sessions_are_logged_with_their_task(focus_env):
    services, clock, _ = focus_env
    task_id = services.tasks.save(None, TaskInput("Problem set 3", due=T0.date()))
    focus = services.focus
    focus.set_focus_task(task_id)
    seen = []
    services.bus.subscribe(seen.append)

    focus.toggle()
    clock.advance(minutes=25)
    event = focus.tick()
    assert event.phase is Phase.WORK and Topic.FOCUS in seen
    clock.advance(minutes=5)
    assert focus.tick().phase is Phase.SHORT_BREAK  # breaks aren't logged

    stats = focus.stats()
    assert (stats.today_sessions, stats.today_minutes) == (1, 25)
    assert (stats.week_sessions, stats.week_minutes) == (1, 25)
    (session,) = services.focus._log.between(T0.date(), T0.date())
    assert session.task_id == task_id and session.started == T0


def test_catching_up_after_sleep_logs_every_missed_session(focus_env):
    services, clock, _ = focus_env
    services.focus.toggle()
    clock.advance(minutes=25 + 5 + 25 + 1)  # the laptop slept through two phase ends
    event = services.focus.tick()
    assert event.phase is Phase.WORK
    assert services.focus.stats().today_sessions == 2


def test_settings_survive_a_restart(focus_env):
    services, clock, path = focus_env
    services.focus.save_settings(FocusSettingsData(50, 10, 20, 3, False))
    again, db = build_services(path, clock, FakeRegister(), MemoryCredentialStore())
    try:
        assert again.focus.settings() == FocusSettingsData(50, 10, 20, 3, False)
        state = again.focus.state()
        assert state.remaining_seconds == 50 * 60 and state.rounds == 3 and not state.started
    finally:
        db.close()


def test_invalid_settings_are_rejected(focus_env):
    services, _, _ = focus_env
    with pytest.raises(ValidationError):
        services.focus.save_settings(FocusSettingsData(work_minutes=0))


def test_candidate_tasks_are_open_and_relevant(focus_env):
    services, _, _ = focus_env
    today = T0.date()
    services.tasks.save(None, TaskInput("Due soon", due=today + timedelta(days=2)))
    services.tasks.save(None, TaskInput("Far away", due=today + timedelta(days=40)))
    services.tasks.save(None, TaskInput("Undated"))
    done = services.tasks.save(None, TaskInput("Already done", due=today))
    services.tasks.set_done(done, True)
    assert [i.task.title for i in services.focus.candidate_tasks()] == ["Due soon", "Undated"]


def test_a_finished_task_stops_being_the_focus(focus_env):
    services, _, _ = focus_env
    task_id = services.tasks.save(None, TaskInput("Essay"))
    services.focus.set_focus_task(task_id)
    services.tasks.set_done(task_id, True)
    assert services.focus.focus_task() is None


def test_state_follows_the_running_timer(focus_env):
    services, clock, _ = focus_env
    services.focus.toggle()
    clock.advance(minutes=10)
    state = services.focus.state()
    assert state.running and state.started and state.phase is Phase.WORK
    assert state.remaining_seconds == 15 * 60 and round(state.progress, 2) == 0.4


def test_ad_hoc_projects_are_logged_and_offered_again(focus_env):
    services, clock, _ = focus_env
    focus = services.focus
    task_id = services.tasks.save(None, TaskInput("Essay"))
    focus.set_focus_task(task_id)
    focus.set_focus_project("  Portfolio   website ")
    assert focus.focus_project() == "Portfolio website" and focus.focus_task() is None

    focus.toggle()
    clock.advance(minutes=25)
    focus.tick()
    clock.advance(minutes=5)
    focus.tick()
    focus.set_focus_task(task_id)  # picking a task clears the project
    assert focus.focus_project() == ""
    clock.advance(minutes=25)
    focus.tick()

    assert focus.recent_projects() == ["Portfolio website"]  # tasks aren't projects
    assert focus.stats().today_by_project == (("Essay", 25), ("Portfolio website", 25))
    focus.set_focus_project("")
    assert focus.focus_project() == "" and focus.focus_task() is None


@pytest.mark.parametrize("end", ["skip", "reset"])
def test_a_session_ended_early_adds_its_minutes_but_not_a_pomodoro(focus_env, end):
    services, clock, _ = focus_env
    focus = services.focus
    focus.set_focus_project("Side project")
    focus.toggle()
    clock.advance(minutes=25)
    focus.tick()  # one full pomodoro
    clock.advance(minutes=5)
    focus.tick()  # the break ends and the next focus session starts
    clock.advance(minutes=12)
    getattr(focus, end)()

    stats = focus.stats()
    assert (stats.today_sessions, stats.today_minutes) == (1, 37)
    assert (stats.week_sessions, stats.week_minutes) == (1, 37)
    assert stats.today_by_project == (("Side project", 37),)
    cut = [s for s in focus._log.between(T0.date(), T0.date()) if not s.complete]
    assert [(s.started, s.minutes) for s in cut] == [(T0 + timedelta(minutes=30), 12)]


def test_skipping_a_break_or_an_unstarted_session_logs_nothing(focus_env):
    services, clock, _ = focus_env
    focus = services.focus
    focus.skip()  # not started
    focus.toggle()
    clock.advance(minutes=2)
    focus.skip()  # 2 minutes of a short break: breaks aren't focus
    assert focus.stats().today_minutes == 0


def test_skipping_after_the_session_already_ran_out_counts_it_as_finished(focus_env):
    services, clock, _ = focus_env
    focus = services.focus
    focus.toggle()
    clock.advance(minutes=25, seconds=1)  # ended, but the UI hasn't ticked yet
    focus.skip()
    stats = focus.stats()
    assert (stats.today_sessions, stats.today_minutes) == (1, 25)
