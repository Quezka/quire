"""Adapter for Classeviva (Spaggiari), the Italian school register.

Uses the REST API behind the Classeviva mobile app. It is not officially
documented; endpoints and headers follow the community reference at
https://github.com/Lioydiano/Classeviva-Official-Endpoints and the
maintained client https://github.com/Lioydiano/Classeviva.
"""
from __future__ import annotations

import html
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
from ..domain import (
    Absence, AbsenceKind, Book, DocumentKind, Notice, NoticeAttachment, SchoolDocument, TaskKind,
)

BASE_URL = "https://web.spaggiari.eu/rest/v1"
HEADERS = {
    "User-Agent": "CVVS/std/4.2.3 Android/12",
    "Z-Dev-Apikey": "Tg1NWEwNGIgIC0K",
    "Content-Type": "application/json",
}
HOMEWORK_CODE = "AGHW"
ABSENCE_CODES = {"ABA0": AbsenceKind.ABSENT, "ABR0": AbsenceKind.LATE,
                 "ABR1": AbsenceKind.SHORT_LATE, "ABU0": AbsenceKind.EARLY_EXIT}
SCHOOL_DAY = "SD"
# Agenda notes ("AGNT") that are really homework.
HOMEWORK_WORDS = re.compile(
    r"\b(compit\w*|eserciz\w*|es\.|pag\.|pagg?\b|pagin\w*|studi\w*|legger\w*|ripass\w*"
    r"|svolger\w*|homework|exercis\w*)", re.IGNORECASE)
# Agenda notes announcing a test rather than homework.
EXAM_WORDS = re.compile(
    r"\b(verific\w*|compit\w* in classe|interrogazion\w*|test|prova|prove|esame|esami"
    r"|simulazione)\b", re.IGNORECASE)


class _OutsideSchoolYear(Exception):
    """Classeviva error 122: the date range falls outside the school year."""


class _WrongUri(Exception):
    """Classeviva error 102: the endpoint doesn't exist (it may have moved)."""


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


def _plain_text(text: str) -> str:
    """Notice text as plain text: some schools write it with HTML markup."""
    if re.search(r"<[a-zA-Z/][^>]*>", text):
        text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", text)
        text = re.sub(r"(?i)<li[^>]*>", "• ", text)
        text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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
        payload = self._send(method, path, body)
        try:
            return json.loads(payload or b"{}")
        except ValueError as e:
            raise RegisterError("Classeviva sent a response Quire couldn't read.") from e

    def _send(self, method: str, path: str, body: dict | None = None) -> bytes:
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
            if e.code == 404 and code.startswith("102"):
                raise _WrongUri(path) from e
            raise RegisterError(f"Classeviva answered with an error ({e.code}"
                                f"{': ' + info if info else ''}).") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise RegisterError(f"Couldn't reach Classeviva ({reason}). "
                                "Check your internet connection.") from e
        return payload

    def _ranged(self, path: str, first: date, last: date) -> dict:
        """GET a dated endpoint, keeping the range inside the school year."""
        window = clamp_to_school_year(first, last, self._today())
        if window is None:
            return {}
        try:
            return self._get(f"{path}/{_stamp(window[0])}/{_stamp(window[1])}")
        except _OutsideSchoolYear:
            return {}

    def _get(self, path: str) -> dict:
        try:
            return self._request("GET", self._student_path(path))
        except _WrongUri as e:
            raise RegisterError(f"Classeviva doesn't know {path.split('/')[1]} any more "
                                "(the endpoint may have moved).") from e

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
        data = self._get("/subjects")
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
            elif HOMEWORK_WORDS.search(text):
                kind = TaskKind.HOMEWORK
            else:
                kind = TaskKind.TASK
            result.append(RemoteAssignment(
                id=str(e["evtId"]), day=_day(e["evtDatetimeBegin"]), kind=kind, text=text,
                subject_id=_id(e.get("subjectId")), subject_name=e.get("subjectDesc") or "",
                author=e.get("authorName") or ""))
        return result

    def homework(self) -> list[RemoteAssignment]:
        """Homework from Classeviva's homework feature ("Compiti", separate from the agenda).

        The endpoint takes no date range and lists what's currently assigned.
        """
        data = self._get("/homeworks")
        result = []
        for h in data.get("items", []):
            due = h.get("expiryDate") or h.get("assignmentDate")
            if not due:
                continue
            result.append(RemoteAssignment(
                id=str(h["evtId"]), day=_day(due), kind=TaskKind.HOMEWORK,
                text=(h.get("homeworkDesc") or "").strip(), subject_id=_id(h.get("subjectId")),
                subject_name=h.get("subjectDesc") or "", author=h.get("teacherName") or "",
                feed="homework", done=bool(h.get("homeworkDone"))))
        return result

    def grades(self) -> list[RemoteGrade]:
        try:
            data = self._request("GET", self._student_path("/grades"))
        except _WrongUri:
            # Some accounts have seen /grades answer "wrong uri" (Lioydiano/Classeviva#31);
            # the overview endpoint carries grades too.
            start, _ = school_year(self._today())
            try:
                data = self._request("GET", self._student_path(
                    f"/overview/all/{_stamp(start)}/{_stamp(self._today())}"))
            except _WrongUri as e:
                raise RegisterError("Classeviva's grades endpoint has moved; Quire needs an "
                                    "update to read grades.") from e
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

    # ---- absences, noticeboard, books, documents, calendar ------------------------

    def absences(self) -> list[Absence]:
        data = self._get("/absences/details")
        result = []
        for e in data.get("events", []):
            kind = ABSENCE_CODES.get(e.get("evtCode") or "")
            if kind is None:
                continue
            hour = e.get("evtHPos")
            result.append(Absence(
                str(e["evtId"]), _day(e["evtDate"]), kind,
                int(hour) if isinstance(hour, int) else None, bool(e.get("isJustified")),
                (e.get("justifReasonDesc") or "").strip(), len(e.get("hoursAbsence") or [])))
        return result

    def notices(self) -> list[Notice]:
        data = self._get("/noticeboard")
        result = []
        for n in data.get("items", []):
            if n.get("cntStatus") == "deleted":
                continue
            code, pub = str(n.get("evtCode") or ""), str(n.get("pubId") or "")
            valid_to = n.get("cntValidTo")
            result.append(Notice(
                f"{code}:{pub}", code, pub, " ".join((n.get("cntTitle") or "").split()),
                n.get("cntCategory") or "",
                _day(n.get("pubDT") or n.get("cntValidFrom") or self._today().isoformat()),
                _day(valid_to) if valid_to else None, bool(n.get("readStatus")),
                tuple(NoticeAttachment(int(a.get("attachNum") or i + 1), a.get("fileName") or "")
                      for i, a in enumerate(n.get("attachments") or []))))
        return result

    def open_notice(self, notice: Notice) -> str:
        # 101 is the "read" action the official app sends; the reply carries the text.
        data = self._request("POST", self._student_path(
            f"/noticeboard/read/{notice.code}/{notice.pub_id}/101"))
        return _plain_text((data.get("item") or {}).get("text") or "")

    def notice_attachment(self, notice: Notice, number: int) -> bytes:
        return self._send("GET", self._student_path(
            f"/noticeboard/attach/{notice.code}/{notice.pub_id}/{number}"))

    def books(self) -> list[Book]:
        data = self._get("/schoolbooks")
        result = []
        for course in data.get("schoolbooks", []):
            for b in course.get("books") or []:
                price = b.get("price")
                result.append(Book(
                    str(b.get("isbnCode") or b.get("bookId") or ""),
                    " ".join((b.get("title") or "").split()), b.get("subjectDesc") or "",
                    b.get("author") or "", b.get("publisher") or "",
                    b.get("volume") or b.get("subheading") or "",
                    float(price) if isinstance(price, (int, float)) else None,
                    bool(b.get("toBuy")), bool(b.get("alreadyOwned")),
                    bool(b.get("newAdoption"))))
        return result

    def documents(self) -> list[SchoolDocument]:
        data = self._request("POST", self._student_path("/documents"))
        result = [SchoolDocument(str(d.get("hash") or ""), (d.get("desc") or "").strip(),
                                 DocumentKind.DOCUMENT)
                  for d in data.get("documents", []) if d.get("hash")]
        result += [SchoolDocument(r.get("viewLink") or r.get("confirmLink") or "",
                                  (r.get("desc") or "").strip(), DocumentKind.REPORT,
                                  r.get("viewLink") or r.get("confirmLink") or "")
                   for r in data.get("schoolReports", [])
                   if r.get("viewLink") or r.get("confirmLink")]
        return result

    def document_file(self, document: SchoolDocument) -> bytes:
        return self._send("POST", self._student_path(f"/documents/read/{document.external_id}"))

    def school_days(self) -> list[date]:
        data = self._get("/calendar/all")
        return [_day(d["dayDate"]) for d in data.get("calendar", [])
                if d.get("dayStatus") == SCHOOL_DAY and d.get("dayDate")]
