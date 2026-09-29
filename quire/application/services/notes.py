from __future__ import annotations

from datetime import date

from ...domain import NotFound, Note, normalize_topic, note_snippet
from ..bus import ChangeBus, Topic
from ..dto import NoteGroup, NoteSummary
from ..inputs import NoteInput
from ..records import NoteRecord, course_record, note_record
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
        by_id = {c.id: course_record(c) for c in self._courses.list()}
        return [NoteSummary(n.id, n.title, n.pinned, n.updated, by_id.get(n.course_id), n.topic,
                            note_snippet(n.body))
                for n in self._notes.search(text.strip(), course_id)]

    def grouped(self, text: str = "", course_id: int | None = None) -> list[NoteGroup]:
        """Notes grouped by course, then topic.

        Courses and topics are alphabetical; notes without a course or topic come last
        in their level. Within a group notes keep the pinned-then-recent order.
        """
        groups: dict[tuple, list[NoteSummary]] = {}
        for summary in self.search(text, course_id):
            course = summary.course
            key = (course is None, course.name.casefold() if course else "",
                   course.id if course else None, summary.topic == "",
                   summary.topic.casefold())
            groups.setdefault(key, []).append(summary)
        return [NoteGroup(notes[0].course, notes[0].topic, tuple(notes))
                for _, notes in sorted(groups.items(), key=lambda kv: kv[0])]

    def topics(self, course_id: int | None) -> list[str]:
        """Topics already used in a course, to suggest when filing a note."""
        return sorted(self._notes.topics(course_id), key=str.casefold)

    def rename_topic(self, course_id: int | None, old: str, new: str) -> int:
        """Rename (or merge into another) topic for every note in a course."""
        old, new = normalize_topic(old), normalize_topic(new)
        if not old or old == new:
            return 0
        changed = self._notes.rename_topic(course_id, old, new)
        self._bus.publish(Topic.NOTES)
        return changed

    def _note(self, note_id: int) -> Note:
        note = self._notes.get(note_id)
        if note is None:
            raise NotFound(f"Note {note_id} does not exist.")
        return note

    def note(self, note_id: int) -> NoteRecord:
        return note_record(self._note(note_id))

    def _canonical_topic(self, course_id: int | None, topic: str) -> str:
        """Reuse an existing topic's spelling when only the letter case differs."""
        topic = normalize_topic(topic)
        existing = {t.casefold(): t for t in self._notes.topics(course_id)}
        return existing.get(topic.casefold(), topic)

    def create(self, body: str = "", course_id: int | None = None, topic: str = "") -> NoteRecord:
        note = Note(body=body, course_id=course_id, updated=self._clock.now(),
                    topic=self._canonical_topic(course_id, topic))
        note.id = self._notes.add(note)
        self._bus.publish(Topic.NOTES)
        return note_record(note)

    def update(self, note_id: int, data: NoteInput) -> NoteRecord:
        """Save an edit; returns the note as stored (e.g. with the topic's canonical spelling)."""
        note = self._note(note_id)
        note.body, note.course_id, note.pinned = data.body, data.course_id, data.pinned
        note.topic = self._canonical_topic(data.course_id, data.topic)
        note.updated = self._clock.now()
        self._notes.update(note)
        self._bus.publish(Topic.NOTES)
        return note_record(note)

    def delete(self, note_id: int):
        self._notes.delete(note_id)
        self._bus.publish(Topic.NOTES)

    def class_note(self, course_id: int, day: date) -> NoteRecord:
        """The note for one lesson of a course, created on first use."""
        course = self._courses.get(course_id)
        if course is None:
            raise NotFound(f"Course {course_id} does not exist.")
        title = class_note_title(course.name, day)
        existing = self._notes.find_by_title(title, course_id)
        return note_record(existing) if existing else self.create(f"# {title}\n\n", course_id)
