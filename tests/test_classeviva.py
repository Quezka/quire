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


def signed_in(routes, today=date(2026, 9, 23)):
    server = FakeServer({"/auth/login": (200, LOGIN), **routes})
    register = ClassevivaRegister(opener=server, today=lambda: today)
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



def test_ranges_are_clamped_to_the_school_year():
    # Asking from late August must not reach before 1 September (error 122 otherwise).
    path = "/students/1234567/agenda/all/20260901/20261231"
    register, server, _ = signed_in({path: (200, AGENDA)})
    register.assignments(date(2026, 8, 24), date(2026, 12, 31))
    assert server.requests[-1].full_url.endswith("/agenda/all/20260901/20261231")


def test_ranges_end_on_30_june():
    path = "/students/1234567/lessons/20270610/20270630"
    register, server, _ = signed_in({path: (200, LESSONS)}, today=date(2027, 6, 20))
    register.lessons(date(2027, 6, 10), date(2027, 9, 30))
    assert server.requests[-1].full_url.endswith("/lessons/20270610/20270630")


def test_summer_holidays_ask_for_nothing():
    register, server, _ = signed_in({}, today=date(2027, 7, 20))
    before = len(server.requests)
    assert register.assignments(date(2027, 7, 1), date(2027, 8, 31)) == []
    assert len(server.requests) == before


def test_invalid_date_range_error_means_no_data():
    path = "/students/1234567/agenda/all/20260923/20261231"
    register, _, _ = signed_in({path: (404, {"statusCode": 404, "info": "Not Found",
                                             "error": "122:CvvRestApi/invalid date range"})})
    assert register.assignments(date(2026, 9, 23), date(2026, 12, 31)) == []


def test_school_year_boundaries():
    from quire.infrastructure.classeviva import school_year
    assert school_year(date(2026, 9, 1)) == (date(2026, 9, 1), date(2027, 6, 30))
    assert school_year(date(2027, 3, 15)) == (date(2026, 9, 1), date(2027, 6, 30))
    assert school_year(date(2026, 8, 31)) == (date(2025, 9, 1), date(2026, 6, 30))
