from __future__ import annotations

from datetime import date, timedelta

from ...domain import Course, Event, NotFound
from ..bus import ChangeBus, Topic
from ..dto import AgendaItem, DayAgenda, ItemKind, TaskItem, WeekAgenda
from ..ports import Clock, CourseRepository, EventRepository, JournalRepository, TaskRepository


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _class_items(courses: list[Course], day: date) -> list[AgendaItem]:
    return [
        AgendaItem(ItemKind.CLASS, c.id, day, slot.time, c.name, c.color,
                   room=c.room_for(slot), teacher=c.teacher)
        for c in courses
        for slot in c.slots_on(day.weekday())
    ]


def _event_item(e: Event) -> AgendaItem:
    return AgendaItem(ItemKind.EVENT, e.id, e.day, e.time, e.title, e.color, details=e.details)


class PlannerService:
    """Use cases for the day planner and the weekly view."""

    def __init__(self, courses: CourseRepository, events: EventRepository,
                 tasks: TaskRepository, journal: JournalRepository, clock: Clock,
                 bus: ChangeBus):
        self._courses = courses
        self._events = events
        self._tasks = tasks
        self._journal = journal
        self._clock = clock
        self._bus = bus

    def today(self) -> date:
        return self._clock.today()

    def day_agenda(self, day: date) -> DayAgenda:
        today = self._clock.today()
        courses = self._courses.list()
        items = _class_items(courses, day) + [_event_item(e) for e in self._events.between(day, day)]
        items.sort(key=lambda i: (i.time.start, i.time.end))

        tasks = self._tasks.due_on(day)
        if day == today:
            # Unfinished work from earlier days follows you to today.
            tasks = self._tasks.open_due_before(day) + tasks
        by_id = {c.id: c for c in courses}
        task_items = tuple(
            TaskItem(t, by_id.get(t.course_id), t.is_overdue(day)) for t in tasks)

        return DayAgenda(day, day == today, tuple(items), task_items,
                         self._journal.get(day), bool(courses))

    def week_agenda(self, any_day: date) -> WeekAgenda:
        monday = monday_of(any_day)
        sunday = monday + timedelta(days=6)
        courses = self._courses.list()
        events = self._events.between(monday, sunday)
        weekend = (any(s.weekday >= 5 for c in courses for s in c.slots)
                   or any(e.day.weekday() >= 5 for e in events))
        days = tuple(monday + timedelta(days=i) for i in range(7 if weekend else 5))

        items = [item for d in days for item in _class_items(courses, d)]
        items += [_event_item(e) for e in events if e.day in days]
        today = self._clock.today()
        today_index = days.index(today) if today in days else None
        return WeekAgenda(days, tuple(items), today_index, bool(courses))

    def event(self, event_id: int) -> Event:
        event = self._events.get(event_id)
        if event is None:
            raise NotFound(f"Event {event_id} does not exist.")
        return event

    def save_event(self, event: Event) -> int:
        event.validate()
        if event.id is None:
            event.id = self._events.add(event)
        else:
            self._events.update(event)
        self._bus.publish(Topic.EVENTS)
        return event.id

    def delete_event(self, event_id: int):
        self._events.delete(event_id)
        self._bus.publish(Topic.EVENTS)

    def journal(self, day: date) -> str:
        return self._journal.get(day)

    def save_journal(self, day: date, body: str):
        self._journal.put(day, body)
        self._bus.publish(Topic.JOURNAL)
