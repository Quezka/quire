"""A pretend Classeviva account, so `quire --demo` can show the School page offline."""
from __future__ import annotations

from datetime import timedelta

from ..application.ports import (
    Credentials, RegisterAccount, RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)
from ..domain import Absence, AbsenceKind, Book, Notice, NoticeAttachment, TaskKind


class DemoRegister:
    """A pretend Classeviva account so `--demo` can show the School page offline."""

    name = "Classeviva"

    def __init__(self, today):
        self.today = today

    def login(self, credentials: Credentials) -> RegisterAccount:
        return RegisterAccount("Giulia Bianchi")

    def subjects(self):
        return [RemoteSubject("1", "MATEMATICA", ("OKAFOR GRACE",)),
                RemoteSubject("2", "BIOLOGY"), RemoteSubject("3", "STORIA", ("DUARTE LUIS",)),
                RemoteSubject("4", "LINGUA STRANIERA INGLESE", ("VALERI ANNA MARIA",))]

    def assignments(self, first, last):
        d = self.today
        return [
            RemoteAssignment("a1", d + timedelta(days=2), TaskKind.HOMEWORK,
                             "Pag. 112 es. 4-9\nRipassare le derivate", "1", "MATEMATICA",
                             "OKAFOR GRACE"),
            RemoteAssignment("a2", d + timedelta(days=5), TaskKind.EXAM,
                             "Verifica: Rivoluzione francese", "3", "STORIA", "DUARTE LUIS"),
        ]

    def homework(self):
        d = self.today
        return [
            RemoteAssignment("h1", d, TaskKind.HOMEWORK, "Workbook p. 18, exercises 1-4",
                             "4", "LINGUA STRANIERA INGLESE", "VALERI ANNA MARIA",
                             feed="homework"),
            RemoteAssignment("h2", d - timedelta(days=3), TaskKind.HOMEWORK,
                             "Riassunto del capitolo 2", "3", "STORIA", "DUARTE LUIS",
                             feed="homework"),
        ]

    def grades(self):
        d = self.today
        marks = [  # (id, days ago, subject id, subject, display, value, type, term, notes)
            ("g1", 70, "1", "MATEMATICA", "6", 6.0, "Scritto", "Trimestre", ""),
            ("g2", 55, "1", "MATEMATICA", "6½", 6.5, "Orale", "Trimestre", ""),
            ("g3", 12, "1", "MATEMATICA", "7½", 7.5, "Scritto", "Pentamestre", ""),
            ("g4", 4, "1", "MATEMATICA", "8", 8.0, "Orale", "Pentamestre", ""),
            ("g5", 60, "3", "STORIA", "6", 6.0, "Orale", "Trimestre", ""),
            ("g6", 20, "3", "STORIA", "5", 5.0, "Scritto", "Pentamestre", ""),
            ("g7", 6, "3", "STORIA", "6-", 5.75, "Orale", "Pentamestre",
             "Ripassare le date principali"),
            ("g8", 50, "2", "BIOLOGY", "8", 8.0, "Scritto", "Trimestre", ""),
            ("g9", 2, "2", "BIOLOGY", "9", 9.0, "Pratico", "Pentamestre", ""),
        ]
        return [RemoteGrade(gid, d - timedelta(days=ago), sid, subject, display, value,
                            kind, period, notes)
                for gid, ago, sid, subject, display, value, kind, period, notes in marks]

    def lessons(self, first, last):
        d = self.today
        return [
            RemoteLesson("l1", d - timedelta(days=1), "1", "MATEMATICA",
                         "Derivate: regola della catena", "OKAFOR GRACE", 1),
            RemoteLesson("l2", d - timedelta(days=1), "3", "STORIA",
                         "La presa della Bastiglia", "DUARTE LUIS", 3),
            RemoteLesson("l3", d - timedelta(days=2), "2", "BIOLOGY",
                         "Cellular respiration: the Krebs cycle", "", 2),
        ]


    def absences(self):
        d = self.today
        return [Absence("a1", d - timedelta(days=9), AbsenceKind.ABSENT, justified=True,
                        reason="Motivi di salute"),
                Absence("a2", d - timedelta(days=4), AbsenceKind.LATE, hour=2),
                Absence("a3", d - timedelta(days=2), AbsenceKind.EARLY_EXIT, hour=5,
                        justified=True, reason="Visita medica")]

    def notices(self):
        d = self.today
        return [
            Notice("CF:1", "CF", "1", "Circolare n. 12 - Uscita didattica al museo", "Circolari",
                   d - timedelta(days=1), d + timedelta(days=10), False,
                   (NoticeAttachment(1, "circolare_12.pdf"),)),
            Notice("CF:2", "CF", "2", "Calendario dei colloqui con i docenti", "Comunicazioni",
                   d - timedelta(days=6), None, True,
                   (NoticeAttachment(1, "colloqui.pdf"), NoticeAttachment(2, "orari.pdf"))),
            Notice("CF:3", "CF", "3", "Assemblea d'istituto", "Circolari",
                   d - timedelta(days=12), None, True),
        ]

    def open_notice(self, notice):
        if notice.code == "CF" and notice.pub_id == "3":
            return ("L'assemblea d'istituto si terrà venerdì in aula magna dalle 10:00 alle 12:00.\n\n"
                    "Le lezioni riprenderanno regolarmente dalla terza ora.")
        return "Vedi allegato."

    def notice_attachment(self, notice, number):
        return b"%PDF-1.4\n% demo\n"

    def books(self):
        return [
            Book("9788808123456", "Matematica.blu 2.0", "MATEMATICA", "Bergamini, Barozzi",
                 "Zanichelli", "Vol. 3", 32.9, to_buy=True),
            Book("9788842123456", "Storia e storiografia", "STORIA", "Desideri, Codovini",
                 "D'Anna", "Vol. 2", 29.5, owned=True),
            Book("9788808654321", "Campbell Biologia", "BIOLOGY", "Reece, Urry", "Pearson",
                 "", 41.0, to_buy=True, new_adoption=True),
        ]

    def documents(self):
        return []

    def document_file(self, document):
        return b""

    def school_days(self):
        start = self.today - timedelta(days=20)
        return [start + timedelta(days=n) for n in range(280)
                if (start + timedelta(days=n)).weekday() < 5]
