from __future__ import annotations

from datetime import date

from ...domain import NotFound, Note
from ..bus import ChangeBus, Topic
from ..dto import NoteSummary
from ..ports import Clock, CourseRepository, NoteRepository


def class_note_title(course_name: str, day: date) -> str:
    return f"{course_name}: {day:%A} {day.day} {day:%B %Y}"


class NoteService:
    """Use cases for markdown notes."""

    def __init__(self, notes: NoteRepository, courses: CourseRepository, clock: Clock,
                 bus: ChangeBus):
        self._notes = notes
        self._courses = courses
        self._clock = clock
        self._bus = bus

    def search(self, text: str = "", course_id: int | None = None) -> list[NoteSummary]:
        """Pinned notes first, then most recently edited."""
        by_id = {c.id: c for c in self._courses.list()}
        return [NoteSummary(n.id, n.title, n.pinned, n.updated, by_id.get(n.course_id))
                for n in self._notes.search(text.strip(), course_id)]

    def note(self, note_id: int) -> Note:
        note = self._notes.get(note_id)
        if note is None:
            raise NotFound(f"Note {note_id} does not exist.")
        return note

    def create(self, body: str = "", course_id: int | None = None) -> Note:
        note = Note(body=body, course_id=course_id, updated=self._clock.now())
        note.id = self._notes.add(note)
        self._bus.publish(Topic.NOTES)
        return note

    def save(self, note: Note):
        note.updated = self._clock.now()
        self._notes.update(note)
        self._bus.publish(Topic.NOTES)

    def delete(self, note_id: int):
        self._notes.delete(note_id)
        self._bus.publish(Topic.NOTES)

    def class_note(self, course_id: int, day: date) -> Note:
        """The note for one lesson of a course, created on first use."""
        course = self._courses.get(course_id)
        if course is None:
            raise NotFound(f"Course {course_id} does not exist.")
        title = class_note_title(course.name, day)
        return self._notes.find_by_title(title, course_id) or self.create(f"# {title}\n\n", course_id)
