"""Absences, the noticeboard, textbooks, documents and the grade tools."""
from datetime import timedelta

import pytest

from quire.application.inputs import CourseInput, SlotInput
from quire.application.ports import RemoteGrade, RemoteSubject
from quire.application.types import AbsenceKind, DocumentKind
from quire.domain import (
    Absence, Book, Notice, NoticeAttachment, SchoolDocument, needed_grade, running_average,
)

from .conftest import TODAY  # a Wednesday

MATHS = RemoteSubject("1", "MATEMATICA", ())


@pytest.fixture
def connected(services, register):
    register.subjects_ = [MATHS]
    services.school_sync.connect("S1234567X", "secret")
    return services


def timetable(services, hours_per_weekday=5):
    """Five one-hour classes Monday to Friday, 8:00-13:00."""
    slots = tuple(SlotInput(day, 480 + 60 * h, 540 + 60 * h)
                  for day in range(5) for h in range(hours_per_weekday))
    services.timetable.save_course(None, CourseInput("Everything", slots=slots))


# ---- domain arithmetic ------------------------------------------------------------------

def test_hours_missed_by_kind():
    day = TODAY
    assert Absence("1", day, AbsenceKind.ABSENT).hours_missed(6) == 6
    assert Absence("2", day, AbsenceKind.LATE, hour=2).hours_missed(6) == 1
    assert Absence("3", day, AbsenceKind.EARLY_EXIT, hour=5).hours_missed(6) == 2
    assert Absence("4", day, AbsenceKind.SHORT_LATE, hour=1).hours_missed(6) == 0
    assert Absence("5", day, AbsenceKind.ABSENT, hours=4).hours_missed(6) == 4  # register knows


def test_needed_grade():
    assert needed_grade([5.0, 5.5], 6.0) == 7.5  # (6*3 - 10.5) / 1
    assert needed_grade([5.0, 5.5], 6.0, tests=2) == 6.75
    assert needed_grade([], 6.0) == 6.0
    assert needed_grade([9, 9, 9], 6.0) < 1  # safe whatever happens
    assert needed_grade([2.0], 7.0) > 10  # can't be done in one test


def test_running_average():
    points = [(TODAY, 6.0), (TODAY - timedelta(days=5), 8.0), (TODAY, 7.0)]
    assert running_average(points) == [(TODAY - timedelta(days=5), 8.0), (TODAY, 7.0)]


# ---- sync and use cases -------------------------------------------------------------

def test_absences_are_counted_against_the_limit(connected, register):
    timetable(connected)
    monday = TODAY - timedelta(days=2)
    register.school_days_ = [monday + timedelta(days=n) for n in range(40)
                             if (monday + timedelta(days=n)).weekday() < 5]  # 30 days
    register.absences_ = [
        Absence("1", monday, AbsenceKind.ABSENT, justified=True, reason="Salute"),
        Absence("2", TODAY, AbsenceKind.LATE, hour=3),
        Absence("3", TODAY + timedelta(days=1), AbsenceKind.EARLY_EXIT, hour=5),
    ]
    report = connected.school_sync.sync()
    assert report.new_absences == 3
    summary = connected.school.absence_summary()
    assert (summary.absent_days, summary.late_entries, summary.early_exits) == (1, 1, 1)
    assert summary.unjustified == 2
    assert summary.hours_missed == 5 + 2 + 1
    assert summary.school_hours == 30 * 5 and summary.limit_hours == 37
    assert summary.hours_left == 29 and round(summary.share, 3) == round(8 / 150, 3)
    assert summary.items[0].kind is AbsenceKind.EARLY_EXIT  # newest first
    assert connected.school_sync.sync().new_absences == 0


def test_an_hour_the_register_left_blank_can_be_entered_and_survives_syncs(connected,
                                                                         register):
    """Classeviva sends `evtHPos: null` when the school didn't record the hour."""
    from quire.domain import ValidationError
    timetable(connected)
    register.absences_ = [Absence("7", TODAY, AbsenceKind.EARLY_EXIT, justified=True)]
    connected.school_sync.sync()
    item = connected.school.absence_summary().items[0]
    assert item.hour is None and item.needs_hour and item.hours_missed == 1

    connected.school.set_absence_hour(item.id, 3)
    item = connected.school.absence_summary().items[0]
    assert (item.hour, item.hour_is_yours, item.hours_missed) == (3, True, 3)

    connected.school_sync.sync()  # the register still has no hour: yours stays
    assert connected.school.absence_summary().items[0].hour == 3

    register.absences_ = [Absence("7", TODAY, AbsenceKind.EARLY_EXIT, hour=4)]
    connected.school_sync.sync()  # the school filled it in later: theirs wins
    item = connected.school.absence_summary().items[0]
    assert (item.hour, item.hour_is_yours, item.needs_hour) == (4, False, False)

    with pytest.raises(ValidationError):
        connected.school.set_absence_hour(item.id, 0)
    connected.school.set_absence_hour(item.id, None)  # forgetting is fine


def test_without_a_calendar_the_year_is_estimated_and_without_a_timetable_unknown(connected,
                                                                                 register):
    register.absences_ = [Absence("1", TODAY, AbsenceKind.ABSENT)]
    connected.school_sync.sync()
    assert connected.school.absence_summary().school_hours == 0
    assert connected.school.absence_summary().share is None
    timetable(connected)
    assert connected.school.absence_summary().school_hours == 25 * 33


def notice(n, read=False, attachments=()):
    return Notice(f"CF:{n}", "CF", str(n), f"Circolare {n}", "Circolari",
                  TODAY - timedelta(days=n), None, read, attachments)


def test_noticeboard_news_read_state_and_attachments(connected, register):
    register.notices_ = [notice(1, attachments=(NoticeAttachment(1, "c1.pdf"),)), notice(2, True)]
    register.files[("CF:1", 1)] = b"%PDF-1"
    first = connected.school_sync.sync()
    assert first.first_sync and set(first.new_notices) == {"Circolare 1", "Circolare 2"}
    assert connected.school.unread_notices() == 1

    (unread, _read) = connected.school.notices()
    assert unread.attachments[0].file_name == "c1.pdf"
    assert connected.school_sync.notice_attachment(unread, 1) == b"%PDF-1"
    register.notice_texts["CF:1"] = "Uscita al museo giovedì."
    assert connected.school_sync.notice_text(unread) == "Uscita al museo giovedì."
    connected.school_sync.mark_notice_read(unread.id)
    assert register.opened == ["CF:1"] and connected.school.unread_notices() == 0

    register.notices_.insert(0, notice(0))
    second = connected.school_sync.sync()
    assert second.new_notices == ("Circolare 0",)
    # Still unread on the register's side, but it was opened here: stays read.
    assert [n.read for n in connected.school.notices()] == [False, True, True]


def test_textbooks_and_documents(connected, register):
    register.books_ = [Book("978B", "Storia 2", "STORIA", to_buy=True, price=29.5),
                       Book("978A", "Algebra", "MATEMATICA", owned=True)]
    register.documents_ = [SchoolDocument("h1", "Pagella primo trimestre", DocumentKind.REPORT,
                                          "https://example.com/pagella"),
                           SchoolDocument("h2", "Certificato", DocumentKind.DOCUMENT)]
    register.files[("h2", 0)] = b"%PDF-2"
    connected.school_sync.sync()
    books = connected.school.books()
    assert [b.title for b in books] == ["Algebra", "Storia 2"]  # by subject
    assert books[1].to_buy and books[1].price == 29.5
    report, document = connected.school.documents()
    assert report.kind is DocumentKind.REPORT and report.link.startswith("https://")
    assert connected.school_sync.document_file(document) == b"%PDF-2"


def test_a_failing_part_keeps_what_was_there(connected, register):
    from quire.application.errors import RegisterError
    register.books_ = [Book("978A", "Algebra", "MATEMATICA")]
    connected.school_sync.sync()
    register.failing["books"] = RegisterError("down")
    report = connected.school_sync.sync()
    assert any(p.startswith("Textbooks") for p in report.problems)
    assert [b.title for b in connected.school.books()] == ["Algebra"]


def mark(n, value, days_ago):
    return RemoteGrade(f"g{n}", TODAY - timedelta(days=days_ago), MATHS.id, MATHS.name,
                       str(value), value, "Scritto", "Trimestre", "", False)


def test_what_do_i_need_and_trend(connected, register):
    register.grades_ = [mark(1, 5.0, 30), mark(2, 5.5, 10)]
    connected.school_sync.sync()
    needed = connected.school.needed("Matematica")
    assert needed.mark == 7.5 and needed.reachable and not needed.already_safe
    assert connected.school.needed("Matematica", tests=2).mark == 6.75
    assert not connected.school.needed("Matematica", target=9.0).reachable
    assert connected.school.needed("Matematica", target=3.0).already_safe
    assert connected.school.trend("Matematica") == [(TODAY - timedelta(days=30), 5.0),
                                                    (TODAY - timedelta(days=10), 5.25)]
    assert connected.school.trend() == connected.school.trend("Matematica")
