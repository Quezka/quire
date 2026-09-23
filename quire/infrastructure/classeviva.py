"""Adapter for Classeviva (Spaggiari), the Italian school register.

Uses the REST API behind the Classeviva mobile app. It is not officially
documented; endpoints and headers follow the community reference at
https://github.com/Lioydiano/Classeviva-Official-Endpoints and the
maintained client https://github.com/Lioydiano/Classeviva.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Callable

from ..application.errors import AuthenticationError, RegisterError
from ..application.ports import (
    Credentials, RegisterAccount, RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)
from ..domain import TaskKind

BASE_URL = "https://web.spaggiari.eu/rest/v1"
HEADERS = {
    "User-Agent": "CVVS/std/4.2.3 Android/12",
    "Z-Dev-Apikey": "Tg1NWEwNGIgIC0K",
    "Content-Type": "application/json",
}
HOMEWORK_CODE = "AGHW"
# Agenda notes announcing a test rather than homework.
EXAM_WORDS = re.compile(
    r"\b(verific\w*|compit\w* in classe|interrogazion\w*|test|prova|prove|esame|esami"
    r"|simulazione)\b", re.IGNORECASE)


class _OutsideSchoolYear(Exception):
    """Classeviva error 122: the date range falls outside the school year."""


def school_year(today: date) -> tuple[date, date]:
    """The school year Classeviva serves data for: 1 September to 30 June."""
    start_year = today.year if today.month >= 9 else today.year - 1
    return date(start_year, 9, 1), date(start_year + 1, 6, 30)


def clamp_to_school_year(first: date, last: date, today: date) -> tuple[date, date] | None:
    """Trim a range to the current school year; None if nothing is left (e.g. summer)."""
    start, end = school_year(today)
    first, last = max(first, start), min(last, end)
    return (first, last) if first <= last else None


def _day(value: str) -> date:
    return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)


def _stamp(d: date) -> str:
    return d.strftime("%Y%m%d")


def _id(value) -> str | None:
    return None if value in (None, "") else str(value)


class ClassevivaRegister:
    name = "Classeviva"

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 20,
                 today: Callable[[], date] = date.today):
        self._open = opener
        self._timeout = timeout
        self._today = today
        self._token: str | None = None
        self._student: str | None = None

    # ---- transport ------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = dict(HEADERS)
        if self._token:
            headers["Z-Auth-Token"] = self._token
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(BASE_URL + path, data=data, headers=headers,
                                         method=method)
        try:
            with self._open(request, timeout=self._timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as e:
            info, code = "", ""
            try:
                detail = json.loads(e.read() or b"{}")
                code = str(detail.get("error") or "")  # e.g. "122:CvvRestApi/invalid date range"
                info = detail.get("info") or code
            except ValueError:
                pass
            if path == "/auth/login" and e.code in (401, 403, 422):
                raise AuthenticationError(
                    "Classeviva didn't accept that username and password.") from e
            if e.code in (401, 403):
                raise AuthenticationError("Your Classeviva session was refused. "
                                          "Try connecting your account again.") from e
            if e.code == 404 and code.startswith("122"):
                raise _OutsideSchoolYear() from e
            raise RegisterError(f"Classeviva answered with an error ({e.code}"
                                f"{': ' + info if info else ''}).") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise RegisterError(f"Couldn't reach Classeviva ({reason}). "
                                "Check your internet connection.") from e
        try:
            return json.loads(payload or b"{}")
        except ValueError as e:
            raise RegisterError("Classeviva sent a response Quire couldn't read.") from e

    def _ranged(self, path: str, first: date, last: date) -> dict:
        """GET a dated endpoint, keeping the range inside the school year."""
        window = clamp_to_school_year(first, last, self._today())
        if window is None:
            return {}
        try:
            return self._request(
                "GET", self._student_path(f"{path}/{_stamp(window[0])}/{_stamp(window[1])}"))
        except _OutsideSchoolYear:
            return {}

    def _student_path(self, path: str) -> str:
        if not self._student:
            raise RegisterError("Not signed in to Classeviva.")
        return f"/students/{self._student}{path}"

    # ---- SchoolRegister -------------------------------------------------------

    def login(self, credentials: Credentials) -> RegisterAccount:
        self._token = None
        body = {"ident": None, "pass": credentials.password, "uid": credentials.username}
        data = self._request("POST", "/auth/login", body)
        if "token" not in data and data.get("choices"):
            # Accounts linked to several profiles (e.g. a parent with two children)
            # must pick one; use the first.
            body["ident"] = data["choices"][0].get("ident")
            data = self._request("POST", "/auth/login", body)
        if not data.get("token"):
            raise RegisterError("Classeviva didn't open a session for this account.")
        self._token = data["token"]
        self._student = re.sub(r"\D", "", data.get("ident") or "")
        if not self._student:
            raise RegisterError("Classeviva didn't say which student this account belongs to.")
        name = " ".join(filter(None, [data.get("firstName"), data.get("lastName")]))
        return RegisterAccount(name.title() if name.isupper() else name)

    def subjects(self) -> list[RemoteSubject]:
        data = self._request("GET", self._student_path("/subjects"))
        return [
            RemoteSubject(str(s["id"]), s.get("description") or "",
                          tuple(t.get("teacherName") or "" for t in s.get("teachers") or []))
            for s in data.get("subjects", [])
        ]

    def assignments(self, first: date, last: date) -> list[RemoteAssignment]:
        data = self._ranged("/agenda/all", first, last)
        result = []
        for e in data.get("agenda", []):
            text = (e.get("notes") or "").strip()
            if e.get("evtCode") == HOMEWORK_CODE:
                kind = TaskKind.HOMEWORK
            elif EXAM_WORDS.search(text):
                kind = TaskKind.EXAM
            else:
                kind = TaskKind.TASK
            result.append(RemoteAssignment(
                id=str(e["evtId"]), day=_day(e["evtDatetimeBegin"]), kind=kind, text=text,
                subject_id=_id(e.get("subjectId")), subject_name=e.get("subjectDesc") or "",
                author=e.get("authorName") or ""))
        return result

    def grades(self) -> list[RemoteGrade]:
        data = self._request("GET", self._student_path("/grades"))
        result = []
        for g in data.get("grades", []):
            value = g.get("decimalValue")
            result.append(RemoteGrade(
                id=str(g["evtId"]), day=_day(g["evtDate"]), subject_id=_id(g.get("subjectId")),
                subject_name=g.get("subjectDesc") or "",
                display=(g.get("displayValue") or "").strip(),
                value=float(value) if isinstance(value, (int, float)) else None,
                component=g.get("componentDesc") or "", period=g.get("periodDesc") or "",
                notes=(g.get("notesForFamily") or "").strip(),
                cancelled=bool(g.get("canceled"))))
        return result

    def lessons(self, first: date, last: date) -> list[RemoteLesson]:
        data = self._ranged("/lessons", first, last)
        seen, result = set(), []
        for l in data.get("lessons", []):
            lesson_id = str(l["evtId"])
            if lesson_id in seen:
                continue
            seen.add(lesson_id)
            result.append(RemoteLesson(
                id=lesson_id, day=_day(l["evtDate"]), subject_id=_id(l.get("subjectId")),
                subject_name=l.get("subjectDesc") or "", topic=(l.get("lessonArg") or "").strip(),
                teacher=l.get("authorName") or "", hour=int(l.get("evtHPos") or 0)))
        return result
