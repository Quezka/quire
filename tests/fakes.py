from dataclasses import dataclass, field
from datetime import date

from quire.application.errors import AuthenticationError
from quire.application.ports import (
    Credentials, RegisterAccount, RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)


@dataclass
class FakeRegister:
    """In-memory stand-in for a school register."""

    name: str = "Classeviva"
    password: str = "secret"
    student: str = "Ada Lovelace"
    subjects_: list[RemoteSubject] = field(default_factory=list)
    assignments_: list[RemoteAssignment] = field(default_factory=list)
    grades_: list[RemoteGrade] = field(default_factory=list)
    lessons_: list[RemoteLesson] = field(default_factory=list)
    requested: list = field(default_factory=list)
    failing: dict = field(default_factory=dict)  # method name -> exception to raise

    def _maybe_fail(self, name):
        if name in self.failing:
            raise self.failing[name]

    def login(self, credentials: Credentials) -> RegisterAccount:
        if credentials.password != self.password:
            raise AuthenticationError("wrong password")
        return RegisterAccount(self.student)

    def subjects(self):
        self._maybe_fail("subjects")
        return list(self.subjects_)

    def assignments(self, first: date, last: date):
        self._maybe_fail("assignments")
        self.requested.append(("assignments", first, last))
        return [a for a in self.assignments_ if first <= a.day <= last]

    def grades(self):
        self._maybe_fail("grades")
        return list(self.grades_)

    def lessons(self, first: date, last: date):
        self._maybe_fail("lessons")
        self.requested.append(("lessons", first, last))
        return [l for l in self.lessons_ if first <= l.day <= last]
