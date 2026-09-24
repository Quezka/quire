from __future__ import annotations

from datetime import date

from ...domain import ClassSlot, Course, NotFound, TimeRange
from ..bus import ChangeBus, Topic
from ..inputs import CourseInput
from ..ports import CourseRepository
from ..records import CourseRecord, course_record


class TimetableService:
    """Use cases for managing courses and their weekly class times."""

    def __init__(self, courses: CourseRepository, bus: ChangeBus):
        self._courses = courses
        self._bus = bus

    def courses(self) -> list[CourseRecord]:
        return [course_record(c) for c in self._courses.list()]

    def _course(self, course_id: int) -> Course:
        course = self._courses.get(course_id)
        if course is None:
            raise NotFound(f"Course {course_id} does not exist.")
        return course

    def course(self, course_id: int) -> CourseRecord:
        return course_record(self._course(course_id))

    def save_course(self, course_id: int | None, data: CourseInput) -> int:
        """Create a course, or change one; its register link is kept."""
        slots = [ClassSlot(s.weekday, TimeRange(s.start, s.end), s.room) for s in data.slots]
        if course_id is None:
            course = Course(data.name.strip(), data.teacher.strip(), data.room.strip(),
                            data.color, slots)
        else:
            course = self._course(course_id)
            course.name, course.teacher = data.name.strip(), data.teacher.strip()
            course.room, course.color, course.slots = data.room.strip(), data.color, slots
        course.validate()
        if course.id is None:
            course.id = self._courses.add(course)
        else:
            self._courses.update(course)
        self._bus.publish(Topic.COURSES)
        return course.id

    def delete_course(self, course_id: int):
        """Delete a course. Its notes and tasks are kept but unlinked."""
        self._courses.delete(course_id)
        self._bus.publish(Topic.COURSES)

    def next_meeting(self, course_id: int, after: date) -> date | None:
        return self._course(course_id).next_meeting_after(after)
