import io
import json
import urllib.error
from datetime import date

import pytest

from quire.application.errors import AuthenticationError, RegisterError
from quire.application.ports import Credentials
from quire.domain import TaskKind
from quire.infrastructure.classeviva import BASE_URL, ClassevivaRegister

LOGIN = {"ident": "S1234567X", "firstName": "MARIO", "lastName": "ROSSI", "token": "tok",
         "release": "2026-09-23T08:00:00+02:00", "expire": "2026-09-23T09:30:00+02:00"}
AGENDA = {"agenda": [
    {"evtId": 1, "evtCode": "AGHW", "evtDatetimeBegin": "2026-09-25T11:00:00+02:00",
     "evtDatetimeEnd": "2026-09-25T12:00:00+02:00", "isFullDay": False,
     "notes": "P. 467 n. 210", "authorName": "BIANCHI ANNA", "subjectId": 206168,
     "subjectDesc": "MATEMATICA", "homeworkId": None},
    {"evtId": 2, "evtCode": "AGNT", "evtDatetimeBegin": "2026-09-28T00:00:00+02:00",
     "notes": "Verifica di storia sul capitolo 2", "authorName": "VERDI", "subjectId": None,
     "subjectDesc": None},
    {"evtId": 3, "evtCode": "AGNT", "evtDatetimeBegin": "2026-09-29T00:00:00+02:00",
     "notes": "Portare il libro", "authorName": "VERDI"},
]}
GRADES = {"grades": [
    {"subjectId": 206166, "subjectDesc": "ARTE", "evtId": 223044, "evtCode": "GRV0",
     "evtDate": "2026-09-20", "decimalValue": 8, "displayValue": "8",
     "notesForFamily": "orale", "canceled": False, "periodDesc": "Trimestre",
     "componentDesc": "Orale"},
    {"subjectId": 206166, "subjectDesc": "ARTE", "evtId": 223045, "evtDate": "2026-09-21",
     "decimalValue": None, "displayValue": "+", "canceled": True},
]}
LESSONS = {"lessons": [
    {"evtId": 5, "evtDate": "2026-09-22", "evtCode": "LSF0", "evtHPos": 2, "authorName": "NERI",
     "subjectId": 206167, "subjectDesc": "FISICA", "lessonArg": "Moto rettilineo"},
    {"evtId": 5, "evtDate": "2026-09-22", "evtHPos": 3, "authorName": "NERI",
     "subjectId": 206167, "subjectDesc": "FISICA", "lessonArg": "Moto rettilineo"},
]}
SUBJECTS = {"subjects": [{"id": 217039, "description": "STORIA", "order": 19,
                          "teachers": [{"teacherId": "A1", "teacherName": "COGNOME NOME"}]}]}


class FakeServer:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        path = request.full_url.removeprefix(BASE_URL)
        status, body = self.routes[path]
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, "err", {},
                                         io.BytesIO(json.dumps(body).encode()))
        return io.BytesIO(json.dumps(body).encode())


def signed_in(routes):
    server = FakeServer({"/auth/login": (200, LOGIN), **routes})
    register = ClassevivaRegister(opener=server)
    account = register.login(Credentials("S1234567X", "pw"))
    return register, server, account


def test_login_sends_expected_request_and_names_student():
    register, server, account = signed_in({})
    request = server.requests[0]
    assert request.get_method() == "POST"
    assert request.get_header("Z-dev-apikey") == "Tg1NWEwNGIgIC0K"
    assert json.loads(request.data) == {"ident": None, "pass": "pw", "uid": "S1234567X"}
    assert account.student_name == "Mario Rossi"


def test_wrong_password_is_an_authentication_error():
    server = FakeServer({"/auth/login": (422, {"info": "WrongCredentials"})})
    with pytest.raises(AuthenticationError):
        ClassevivaRegister(opener=server).login(Credentials("x", "y"))


def test_network_failure_is_a_register_error():
    def offline(request, timeout):
        raise urllib.error.URLError("no route to host")
    with pytest.raises(RegisterError, match="internet"):
        ClassevivaRegister(opener=offline).login(Credentials("x", "y"))


def test_agenda_is_parsed_and_classified():
    path = "/students/1234567/agenda/all/20260901/20261231"
    register, server, _ = signed_in({path: (200, AGENDA)})
    items = register.assignments(date(2026, 9, 1), date(2026, 12, 31))
    assert server.requests[-1].get_header("Z-auth-token") == "tok"
    assert [(i.id, i.kind, i.day) for i in items] == [
        ("1", TaskKind.HOMEWORK, date(2026, 9, 25)),
        ("2", TaskKind.EXAM, date(2026, 9, 28)),
        ("3", TaskKind.TASK, date(2026, 9, 29)),
    ]
    assert items[0].subject_id == "206168" and items[1].subject_id is None


def test_grades_are_parsed():
    register, _, _ = signed_in({"/students/1234567/grades": (200, GRADES)})
    first, second = register.grades()
    assert (first.value, first.display, first.component, first.notes) == (8.0, "8", "Orale", "orale")
    assert second.value is None and second.cancelled


def test_lessons_are_deduplicated():
    register, _, _ = signed_in({"/students/1234567/lessons/20260915/20260923": (200, LESSONS)})
    (lesson,) = register.lessons(date(2026, 9, 15), date(2026, 9, 23))
    assert (lesson.topic, lesson.hour, lesson.teacher) == ("Moto rettilineo", 2, "NERI")


def test_subjects_are_parsed():
    register, _, _ = signed_in({"/students/1234567/subjects": (200, SUBJECTS)})
    (subject,) = register.subjects()
    assert subject.name == "STORIA" and subject.teachers == ("COGNOME NOME",)


def test_calls_before_login_fail_clearly():
    with pytest.raises(RegisterError, match="Not signed in"):
        ClassevivaRegister(opener=FakeServer({})).grades()
