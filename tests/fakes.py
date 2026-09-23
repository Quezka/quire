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

    def login(self, credentials: Credentials) -> RegisterAccount:
        if credentials.password != self.password:
            raise AuthenticationError("wrong password")
        return RegisterAccount(self.student)

    def subjects(self):
        return list(self.subjects_)

    def assignments(self, first: date, last: date):
        self.requested.append(("assignments", first, last))
        return [a for a in self.assignments_ if first <= a.day <= last]

    def grades(self):
        return list(self.grades_)

    def lessons(self, first: date, last: date):
        self.requested.append(("lessons", first, last))
        return [l for l in self.lessons_ if first <= l.day <= last]
