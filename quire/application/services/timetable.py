from __future__ import annotations

from datetime import date

from ...domain import Course, NotFound
from ..bus import ChangeBus, Topic
from ..ports import CourseRepository


class TimetableService:
    """Use cases for managing courses and their weekly class times."""

    def __init__(self, courses: CourseRepository, bus: ChangeBus):
        self._courses = courses
        self._bus = bus

    def courses(self) -> list[Course]:
        return self._courses.list()

    def course(self, course_id: int) -> Course:
        course = self._courses.get(course_id)
        if course is None:
            raise NotFound(f"Course {course_id} does not exist.")
        return course

    def save_course(self, course: Course) -> int:
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
        return self.course(course_id).next_meeting_after(after)
