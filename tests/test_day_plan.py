from quire.domain.day_plan import Slot, free_gaps, plan, round_up


def test_gaps_leave_room_around_whats_on():
    assert free_gaps([(9 * 60, 10 * 60)], 8 * 60, 12 * 60) == [(480, 530), (610, 720)]
    assert free_gaps([], 480, 600) == [(480, 600)]
    assert free_gaps([(400, 700)], 480, 600) == []


def test_tasks_go_in_order_into_the_first_stretch_they_fit():
    busy = [(8 * 60 + 30, 12 * 60), (13 * 60, 14 * 60)]
    slots = plan([(1, "Essay"), (2, "Maths"), (3, "Call")], busy, 8 * 60, 18 * 60)
    # 8:00-8:20 and 12:10-12:50 too short for 45 min
    assert slots[0] == Slot(14 * 60 + 10, 14 * 60 + 55, "Essay", 1)
    assert [s.start for s in slots[1:]] == [15 * 60 + 5, 16 * 60]


def test_never_more_than_four_and_nothing_when_full():
    assert len(plan([(i, str(i)) for i in range(9)], [], 8 * 60, 22 * 60)) == 4
    assert plan([(1, "x")], [(0, 1440)]) == []
    assert round_up(8 * 60 + 1) == 8 * 60 + 15 and round_up(480) == 480


def test_plan_my_day_fits_due_tasks_around_whats_on_and_saves_only_whats_accepted(services):
    from datetime import timedelta
    from quire.application.inputs import EventInput, RoutineInput, TaskInput
    from .conftest import TODAY
    day = TODAY + timedelta(days=1)
    services.planner.save_event(None, EventInput(day, 8 * 60, 13 * 60, "School"))
    services.planner.save_routine(None, RoutineInput("Shower", 13 * 60, minutes=30))
    services.planner.save_routine(None, RoutineInput("Wake up", 7 * 60))  # a moment: takes no room
    services.tasks.save(None, TaskInput("Essay", due=day))
    services.tasks.save(None, TaskInput("Maths", due=day))
    slots = services.planner.suggest_day(day)
    assert [s.title for s in slots] == ["Essay", "Maths"]
    assert slots[0].start >= 13 * 60 + 40  # after the shower + room
    assert services.planner.accept_plan(day, slots[:1]) == 1
    titles = [i.title for i in services.planner.day_agenda(day).items]
    assert "Essay" in titles and "Maths" not in titles
