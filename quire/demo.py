"""Sample data for `quire --demo`, created through the application's use cases."""
from __future__ import annotations

from datetime import timedelta

from .application.ports import (
    Credentials, RegisterAccount, RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)
from .application.services import Services
from .domain import ClassSlot, Course, Event, Job, Shift, Task, TaskKind, TimeRange


def _t(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _range(start: str, end: str) -> TimeRange:
    return TimeRange(_t(start), _t(end))


def seed(services: Services):
    today = services.planner.today()
    monday = today - timedelta(days=today.weekday())

    timetable = [
        ("Mathematics", "Ms. Okafor", "B12", "#4f7cff",
         [(0, "08:30", "09:20"), (2, "08:30", "09:20"), (4, "10:30", "11:20")]),
        ("Biology", "Mr. Lindqvist", "Lab 2", "#30a46c",
         [(0, "09:30", "10:20"), (3, "13:00", "14:30")]),
        ("English Literature", "Mrs. Patel", "A04", "#8e4ec6",
         [(1, "08:30", "09:20"), (3, "08:30", "09:20"), (4, "08:30", "09:20")]),
        ("History", "Mr. Duarte", "C07", "#f5a524", [(1, "10:30", "11:20"), (4, "13:00", "13:50")]),
        ("Chemistry", "Dr. Nakamura", "Lab 1", "#e5484d",
         [(0, "13:00", "14:30"), (2, "10:30", "11:20")]),
        ("PE", "Coach Rivera", "Gym", "#12a594", [(2, "14:00", "15:30")]),
    ]
    ids = {}
    for name, teacher, room, color, slots in timetable:
        course = Course(name, teacher, room, color,
                        [ClassSlot(wd, _range(s, e)) for wd, s, e in slots])
        ids[name] = services.timetable.save_course(course)

    planner = services.planner
    planner.save_event(Event(today, _range("12:00", "12:45"), "Lunch with Sam", color="#978365"))
    planner.save_event(Event(today, _range("16:00", "17:30"), "Study group",
                             "Library, 2nd floor", "#0090ff"))
    planner.save_event(Event(monday + timedelta(days=4), _range("17:00", "19:00"),
                             "Football practice", color="#12a594"))

    tasks = [
        ("Problem set 3 (q1–12)", TaskKind.HOMEWORK, "Mathematics", 1),
        ("Read chapters 5–6 of Frankenstein", TaskKind.READING, "English Literature", 3),
        ("Cell respiration lab report", TaskKind.ASSIGNMENT, "Biology", 6),
        ("Unit test: Industrial Revolution", TaskKind.EXAM, "History", 9),
        ("Titration pre-lab questions", TaskKind.HOMEWORK, "Chemistry", -1),
        ("Buy a new graphing calculator", TaskKind.TASK, None, 0),
        ("Return library books", TaskKind.TASK, None, None),
    ]
    for title, kind, course, offset in tasks:
        due = today + timedelta(days=offset) if offset is not None else None
        services.tasks.save(Task(title, kind, ids.get(course), due))
    services.tasks.save(Task("Vocabulary list 4", TaskKind.HOMEWORK, ids["English Literature"],
                             today - timedelta(days=2), done=True))

    notes = services.notes
    notes.create(
        "# Biology: cellular respiration\n\n"
        "**Equation:** C6H12O6 + 6 O2 → 6 CO2 + 6 H2O + energy (ATP)\n\n"
        "## Stages\n"
        "1. Glycolysis: cytoplasm, 2 ATP\n"
        "2. Krebs cycle: mitochondrial matrix\n"
        "3. Electron transport chain: inner membrane, ~34 ATP\n\n"
        "- [x] Review diagram on p. 112\n"
        "- [ ] Ask about anaerobic pathways\n",
        ids["Biology"], "Cell biology")
    notes.create("# Mitochondria\n\nThe powerhouse of the cell: inner membrane folds (cristae) "
                 "increase surface area for the electron transport chain.\n",
                 ids["Biology"], "Cell biology")
    notes.create("# Mendel's laws\n\n1. Segregation\n2. Independent assortment\n",
                 ids["Biology"], "Genetics")
    notes.create(
        "# Frankenstein: themes\n\n"
        "- Ambition and its costs\n- Isolation\n- *Nature vs. nurture*\n\n"
        "> \"Beware; for I am fearless, and therefore powerful.\"\n",
        ids["English Literature"], "Frankenstein")
    ideas = notes.create("# Ideas\n\nThings I want to try this term:\n\n"
                         "- Pomodoro for maths homework\n- Join the robotics club\n")
    ideas.pinned = True
    notes.save(ideas)
    planner.save_journal(today, "Remember to bring the permission slip for the museum trip.")

    work = services.work
    pizzeria = work.save_job(Job("Pizzeria Da Mario", "#f76b15", 8.5))
    tutoring = work.save_job(Job("Maths tutoring", "#12a594", 15.0))
    work.save_shift(Shift.between(pizzeria, monday + timedelta(days=1), _t("18:00"), _t("22:30"),
                                  break_minutes=30), repeat_weeks=3)
    work.save_shift(Shift.between(pizzeria, monday + timedelta(days=5), _t("19:00"), _t("01:00"),
                                  break_minutes=30, notes="Saturday rush"), repeat_weeks=3)
    work.save_shift(Shift.between(tutoring, monday + timedelta(days=3), _t("16:00"),
                                  _t("17:30")), repeat_weeks=3)


class DemoRegister:
    """A pretend Classeviva account so `--demo` can show the School page offline."""

    name = "Classeviva"

    def __init__(self, today):
        self.today = today

    def login(self, credentials: Credentials) -> RegisterAccount:
        return RegisterAccount("Giulia Bianchi")

    def subjects(self):
        return [RemoteSubject("1", "MATEMATICA", ("OKAFOR GRACE",)),
                RemoteSubject("2", "BIOLOGY"), RemoteSubject("3", "STORIA", ("DUARTE LUIS",))]

    def assignments(self, first, last):
        d = self.today
        return [
            RemoteAssignment("a1", d + timedelta(days=2), TaskKind.HOMEWORK,
                             "Pag. 112 es. 4-9\nRipassare le derivate", "1", "MATEMATICA",
                             "OKAFOR GRACE"),
            RemoteAssignment("a2", d + timedelta(days=5), TaskKind.EXAM,
                             "Verifica: Rivoluzione francese", "3", "STORIA", "DUARTE LUIS"),
        ]

    def grades(self):
        d = self.today
        return [
            RemoteGrade("g1", d - timedelta(days=12), "1", "MATEMATICA", "7½", 7.5, "Scritto"),
            RemoteGrade("g2", d - timedelta(days=4), "1", "MATEMATICA", "8", 8.0, "Orale"),
            RemoteGrade("g3", d - timedelta(days=6), "3", "STORIA", "6-", 5.75, "Orale",
                        notes="Ripassare le date principali"),
            RemoteGrade("g4", d - timedelta(days=2), "2", "BIOLOGY", "9", 9.0, "Pratico"),
        ]

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


def seed_school(services: Services):
    services.school.connect("demo", "demo")
    services.school.sync()
