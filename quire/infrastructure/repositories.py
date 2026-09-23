"""SQLite implementations of the application's repository ports."""
from __future__ import annotations

from datetime import date, datetime

from ..domain import ClassSlot, Course, Event, Note, Task, TaskKind, TimeRange
from .sqlite import SqliteDatabase


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class _Repo:
    def __init__(self, db: SqliteDatabase):
        self._conn = db.conn

    def _all(self, sql, *args):
        return self._conn.execute(sql, args).fetchall()

    def _one(self, sql, *args):
        return self._conn.execute(sql, args).fetchone()

    def _write(self, sql, *args) -> int:
        with self._conn:
            return self._conn.execute(sql, args).lastrowid


class SqliteCourseRepository(_Repo):
    def _load(self, rows) -> list[Course]:
        courses = {r["id"]: Course(r["name"], r["teacher"], r["room"], r["color"], [], r["id"])
                   for r in rows}
        if courses:
            marks = ",".join("?" * len(courses))
            for s in self._all(f"SELECT * FROM class_slots WHERE course_id IN ({marks})"
                               " ORDER BY weekday, start_min", *courses):
                courses[s["course_id"]].slots.append(
                    ClassSlot(s["weekday"], TimeRange(s["start_min"], s["end_min"]), s["room"]))
        return list(courses.values())

    def list(self) -> list[Course]:
        return self._load(self._all("SELECT * FROM courses ORDER BY name COLLATE NOCASE"))

    def get(self, course_id):
        found = self._load(self._all("SELECT * FROM courses WHERE id = ?", course_id))
        return found[0] if found else None

    def _write_slots(self, course: Course):
        self._conn.execute("DELETE FROM class_slots WHERE course_id = ?", (course.id,))
        self._conn.executemany(
            "INSERT INTO class_slots (course_id, weekday, start_min, end_min, room)"
            " VALUES (?, ?, ?, ?, ?)",
            [(course.id, s.weekday, s.time.start, s.time.end, s.room) for s in course.slots])

    def add(self, course: Course) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO courses (name, teacher, room, color) VALUES (?, ?, ?, ?)",
                (course.name, course.teacher, course.room, course.color))
            course.id = cur.lastrowid
            self._write_slots(course)
        return course.id

    def update(self, course: Course):
        with self._conn:
            self._conn.execute(
                "UPDATE courses SET name = ?, teacher = ?, room = ?, color = ? WHERE id = ?",
                (course.name, course.teacher, course.room, course.color, course.id))
            self._write_slots(course)

    def delete(self, course_id):
        self._write("DELETE FROM courses WHERE id = ?", course_id)


class SqliteEventRepository(_Repo):
    @staticmethod
    def _event(r) -> Event:
        return Event(date.fromisoformat(r["day"]), TimeRange(r["start_min"], r["end_min"]),
                     r["title"], r["details"], r["color"], r["id"])

    def between(self, first, last):
        rows = self._all("SELECT * FROM events WHERE day BETWEEN ? AND ? ORDER BY day, start_min",
                         first.isoformat(), last.isoformat())
        return [self._event(r) for r in rows]

    def get(self, event_id):
        r = self._one("SELECT * FROM events WHERE id = ?", event_id)
        return self._event(r) if r else None

    def add(self, e: Event) -> int:
        return self._write(
            "INSERT INTO events (day, start_min, end_min, title, details, color)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            e.day.isoformat(), e.time.start, e.time.end, e.title, e.details, e.color)

    def update(self, e: Event):
        self._write(
            "UPDATE events SET day = ?, start_min = ?, end_min = ?, title = ?, details = ?,"
            " color = ? WHERE id = ?",
            e.day.isoformat(), e.time.start, e.time.end, e.title, e.details, e.color, e.id)

    def delete(self, event_id):
        self._write("DELETE FROM events WHERE id = ?", event_id)


class SqliteTaskRepository(_Repo):
    _ORDER = " ORDER BY due IS NULL, due, title COLLATE NOCASE"

    @staticmethod
    def _task(r) -> Task:
        try:
            kind = TaskKind(r["kind"])
        except ValueError:
            kind = TaskKind.TASK
        return Task(r["title"], kind, r["course_id"], _date(r["due"]), bool(r["done"]),
                    r["details"], r["id"])

    def list(self, include_done=True, course_id=None):
        where, args = [], []
        if not include_done:
            where.append("done = 0")
        if course_id is not None:
            where.append("course_id = ?")
            args.append(course_id)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "")
        return [self._task(r) for r in self._all(sql + self._ORDER, *args)]

    def due_on(self, day):
        return [self._task(r) for r in
                self._all("SELECT * FROM tasks WHERE due = ?" + self._ORDER, day.isoformat())]

    def open_due_before(self, day):
        return [self._task(r) for r in
                self._all("SELECT * FROM tasks WHERE due < ? AND done = 0" + self._ORDER,
                          day.isoformat())]

    def get(self, task_id):
        r = self._one("SELECT * FROM tasks WHERE id = ?", task_id)
        return self._task(r) if r else None

    def add(self, t: Task) -> int:
        return self._write(
            "INSERT INTO tasks (title, kind, course_id, due, done, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            t.title, t.kind.value, t.course_id, t.due.isoformat() if t.due else None,
            int(t.done), t.details)

    def update(self, t: Task):
        self._write(
            "UPDATE tasks SET title = ?, kind = ?, course_id = ?, due = ?, done = ?, details = ?"
            " WHERE id = ?",
            t.title, t.kind.value, t.course_id, t.due.isoformat() if t.due else None,
            int(t.done), t.details, t.id)

    def delete(self, task_id):
        self._write("DELETE FROM tasks WHERE id = ?", task_id)


class SqliteNoteRepository(_Repo):
    @staticmethod
    def _note(r) -> Note:
        return Note(r["body"], r["course_id"], bool(r["pinned"]),
                    datetime.fromisoformat(r["updated"]) if r["updated"] else None, r["id"])

    def search(self, text="", course_id=None):
        where, args = [], []
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("body LIKE ? ESCAPE '\\'")
            args.append(f"%{escaped}%")
        if course_id is not None:
            where.append("course_id = ?")
            args.append(course_id)
        sql = "SELECT * FROM notes" + (" WHERE " + " AND ".join(where) if where else "")
        return [self._note(r) for r in
                self._all(sql + " ORDER BY pinned DESC, updated DESC, id DESC", *args)]

    def find_by_title(self, title, course_id):
        r = self._one("SELECT * FROM notes WHERE title = ? AND course_id IS ? ORDER BY id LIMIT 1",
                      title, course_id)
        return self._note(r) if r else None

    def get(self, note_id):
        r = self._one("SELECT * FROM notes WHERE id = ?", note_id)
        return self._note(r) if r else None

    @staticmethod
    def _updated(n: Note) -> str:
        return (n.updated or datetime.now()).isoformat(timespec="seconds")

    def add(self, n: Note) -> int:
        return self._write(
            "INSERT INTO notes (title, body, course_id, pinned, updated) VALUES (?, ?, ?, ?, ?)",
            n.title, n.body, n.course_id, int(n.pinned), self._updated(n))

    def update(self, n: Note):
        self._write(
            "UPDATE notes SET title = ?, body = ?, course_id = ?, pinned = ?, updated = ?"
            " WHERE id = ?",
            n.title, n.body, n.course_id, int(n.pinned), self._updated(n), n.id)

    def delete(self, note_id):
        self._write("DELETE FROM notes WHERE id = ?", note_id)


class SqliteJournalRepository(_Repo):
    def get(self, day):
        r = self._one("SELECT body FROM journal WHERE day = ?", day.isoformat())
        return r["body"] if r else ""

    def put(self, day, body):
        if body.strip():
            self._write("INSERT INTO journal (day, body) VALUES (?, ?)"
                        " ON CONFLICT(day) DO UPDATE SET body = excluded.body",
                        day.isoformat(), body)
        else:
            self._write("DELETE FROM journal WHERE day = ?", day.isoformat())
