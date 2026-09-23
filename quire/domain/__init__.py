"""Enterprise business rules: entities and invariants, free of any framework."""
from .errors import DomainError, NotFound, ValidationError
from .model import (
    COURSE_COLORS, UPCOMING_DAYS, ClassSlot, Course, DueBucket, Event, Grade, Lesson, Note, Task, TaskKind,
    TimeRange, average, derive_note_title, normalize_topic,
)

__all__ = [
    "DomainError", "NotFound", "ValidationError", "COURSE_COLORS", "UPCOMING_DAYS", "ClassSlot", "Course",
    "DueBucket", "Event", "Grade", "Lesson", "Note", "Task", "TaskKind", "TimeRange", "average",
    "derive_note_title", "normalize_topic",
]
