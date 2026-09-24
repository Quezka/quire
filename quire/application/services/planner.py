from __future__ import annotations

from datetime import date, timedelta

from ...domain import Course, Event, NotFound, TimeRange, work_shifts
from ..bus import ChangeBus, Topic
from ..dto import AgendaItem, DayAgenda, ItemKind, TaskItem, WeekAgenda
from ..inputs import EventInput
from ..records import EventRecord, course_record, event_record, span, task_record
from ..ports import (
    Clock, CourseRepository, EventRepository, JobRepository, JournalRepository, ShiftRepository,
    TaskRepository,
)
from .work import shift_agenda_items


UPCOMING_TASK_DAYS = 14


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _class_items(courses: list[Course], day: date) -> list[AgendaItem]:
    return [
        AgendaItem(ItemKind.CLASS, c.id, day, span(slot.time), c.name, c.color,
                   room=c.room_for(slot), teacher=c.teacher)
        for c in courses
        for slot in c.slots_on(day.weekday())
    ]


def _event_item(e: Event) -> AgendaItem:
    return AgendaItem(ItemKind.EVENT, e.id, e.day, span(e.time), e.title, e.color,
                      details=e.details)


class PlannerService:
    """Use cases for the day planner and the weekly view."""

    def __init__(self, courses: CourseRepository, events: EventRepository,
                 tasks: TaskRepository, journal: JournalRepository, clock: Clock,
                 bus: ChangeBus, jobs: JobRepository, shifts: ShiftRepository):
        self._jobs = jobs
        self._shifts = shifts
        self._courses = courses
        self._events = events
        self._tasks = tasks
        self._journal = journal
        self._clock = clock
        self._bus = bus

    def today(self) -> date:
        return self._clock.today()

    def _shift_items(self, first: date, last: date) -> list[AgendaItem]:
        """Shift segments on days first..last (a shift may start the evening before)."""
        jobs = self._jobs.list()
        by_id = {j.id: j for j in jobs}
        start = first - timedelta(days=1)
        shifts = work_shifts(jobs, self._shifts.starting_between(start, last),
                             self._shifts.skipped(start, last), start, last)
        items = shift_agenda_items([(s, by_id.get(s.job_id)) for s in shifts])
        return [i for i in items if first <= i.day <= last]

    def items_between(self, first: date, last: date) -> list[AgendaItem]:
        """Every class, event and shift segment on days first..last."""
        courses = self._courses.list()
        days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
        return ([i for d in days for i in _class_items(courses, d)]
                + [_event_item(e) for e in self._events.between(first, last)]
                + self._shift_items(first, last))

    def day_agenda(self, day: date) -> DayAgenda:
        today = self._clock.today()
        courses = self._courses.list()
        items = (_class_items(courses, day)
                 + [_event_item(e) for e in self._events.between(day, day)]
                 + self._shift_items(day, day))
        items.sort(key=lambda i: (i.time.start, i.time.end))

        tasks = self._tasks.due_on(day)
        if day == today:
            # Today shows everything still to do: unfinished work from earlier days,
            # today's, and what's coming up in the next UPCOMING_TASK_DAYS days.
            ahead = [t for t in self._tasks.list(include_done=False)
                     if t.due is not None and 0 < (t.due - day).days <= UPCOMING_TASK_DAYS]
            tasks = self._tasks.open_due_before(day) + tasks + sorted(
                ahead, key=lambda t: (t.due, t.title.casefold()))
        by_id = {c.id: c for c in courses}
        task_items = tuple(
            TaskItem(task_record(t), course_record(by_id[t.course_id]) if t.course_id in by_id
                     else None, t.is_overdue(day))
            for t in tasks)

        return DayAgenda(day, day == today, tuple(items), task_items,
                         self._journal.get(day), bool(courses))

    def week_agenda(self, any_day: date) -> WeekAgenda:
        monday = monday_of(any_day)
        sunday = monday + timedelta(days=6)
        courses = self._courses.list()
        events = self._events.between(monday, sunday)
        shifts = self._shift_items(monday, sunday)
        weekend = (any(s.weekday >= 5 for c in courses for s in c.slots)
                   or any(e.day.weekday() >= 5 for e in events)
                   or any(i.day.weekday() >= 5 for i in shifts))
        days = tuple(monday + timedelta(days=i) for i in range(7 if weekend else 5))

        items = [item for d in days for item in _class_items(courses, d)]
        items += [_event_item(e) for e in events if e.day in days]
        items += [i for i in shifts if i.day in days]
        today = self._clock.today()
        today_index = days.index(today) if today in days else None
        return WeekAgenda(days, tuple(items), today_index, bool(courses))

    def _event(self, event_id: int) -> Event:
        event = self._events.get(event_id)
        if event is None:
            raise NotFound(f"Event {event_id} does not exist.")
        return event

    def event(self, event_id: int) -> EventRecord:
        return event_record(self._event(event_id))

    def save_event(self, event_id: int | None, data: EventInput) -> int:
        time = TimeRange(data.start, data.end)
        if event_id is None:
            event = Event(data.day, time, data.title.strip(), data.details, data.color)
        else:
            event = self._event(event_id)
            event.day, event.time, event.title = data.day, time, data.title.strip()
            event.details, event.color = data.details, data.color
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
