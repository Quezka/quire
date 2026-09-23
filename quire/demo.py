"""Sample data for `quire --demo`, created through the application's use cases."""
from __future__ import annotations

from datetime import timedelta

from .application.services import Services
from .domain import ClassSlot, Course, Event, Task, TaskKind, TimeRange


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
        ids["Biology"])
    notes.create(
        "# Frankenstein: themes\n\n"
        "- Ambition and its costs\n- Isolation\n- *Nature vs. nurture*\n\n"
        "> \"Beware; for I am fearless, and therefore powerful.\"\n",
        ids["English Literature"])
    ideas = notes.create("# Ideas\n\nThings I want to try this term:\n\n"
                         "- Pomodoro for maths homework\n- Join the robotics club\n")
    ideas.pinned = True
    notes.save(ideas)
    planner.save_journal(today, "Remember to bring the permission slip for the museum trip.")
