"""Framework-free change notifications, so outer layers can react to writes."""
from __future__ import annotations

from enum import Enum
from typing import Callable


class Topic(Enum):
    COURSES = "courses"
    EVENTS = "events"
    TASKS = "tasks"
    NOTES = "notes"
    JOURNAL = "journal"
    SCHOOL = "school"
    WORK = "work"
    FOCUS = "focus"


Listener = Callable[[Topic], None]


class ChangeBus:
    def __init__(self):
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def publish(self, topic: Topic):
        for listener in list(self._listeners):
            listener(topic)
