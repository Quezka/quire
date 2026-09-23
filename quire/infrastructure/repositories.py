"""SQLite implementations of the application's repository ports."""
from __future__ import annotations

from datetime import date, datetime

from ..domain import ClassSlot, Course, Event, Grade, Lesson, Note, Subject, Task, TaskKind, TimeRange
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
        courses = {r["id"]: Course(r["name"], r["teacher"], r["room"], r["color"], [], r["id"],
                                   r["external_id"])
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
                "INSERT INTO courses (name, teacher, room, color, external_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (course.name, course.teacher, course.room, course.color, course.external_id))
            course.id = cur.lastrowid
            self._write_slots(course)
        return course.id

    def update(self, course: Course):
        with self._conn:
            self._conn.execute(
                "UPDATE courses SET name = ?, teacher = ?, room = ?, color = ?, external_id = ?"
                " WHERE id = ?",
                (course.name, course.teacher, course.room, course.color, course.external_id,
                 course.id))
            self._write_slots(course)

    def delete(self, course_id):
        self._write("DELETE FROM courses WHERE id = ?", course_id)

    def merge_into(self, source_id, target_id):
        with self._conn:
            for table in ("tasks", "notes", "grades", "lessons"):
                self._conn.execute(f"UPDATE {table} SET course_id = ? WHERE course_id = ?",
                                   (target_id, source_id))
            self._conn.execute("DELETE FROM courses WHERE id = ?", (source_id,))


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
                    r["details"], r["id"], r["external_id"])

    def list(self, include_done=True, course_id=None):
        where, args = [], []
        if not include_done:
            where.append("done = 0")
        if course_id is not None:
            where.append("course_id = ?")
            args.append(course_id)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "")
        return [self._task(r) for r in self._all(sql + self._ORDER, *args)]

    def by_external_prefix(self, prefix):
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return [self._task(r) for r in
                self._all("SELECT * FROM tasks WHERE external_id LIKE ? ESCAPE '\\'",
                          escaped + "%")]

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
            "INSERT INTO tasks (title, kind, course_id, due, done, details, external_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            t.title, t.kind.value, t.course_id, t.due.isoformat() if t.due else None,
            int(t.done), t.details, t.external_id)

    def update(self, t: Task):
        self._write(
            "UPDATE tasks SET title = ?, kind = ?, course_id = ?, due = ?, done = ?, details = ?,"
            " external_id = ? WHERE id = ?",
            t.title, t.kind.value, t.course_id, t.due.isoformat() if t.due else None,
            int(t.done), t.details, t.external_id, t.id)

    def delete(self, task_id):
        self._write("DELETE FROM tasks WHERE id = ?", task_id)


class SqliteNoteRepository(_Repo):
    @staticmethod
    def _note(r) -> Note:
        return Note(r["body"], r["course_id"], bool(r["pinned"]),
                    datetime.fromisoformat(r["updated"]) if r["updated"] else None, r["id"],
                    r["topic"])

    def search(self, text="", course_id=None):
        where, args = [], []
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(body LIKE ? ESCAPE '\\' OR topic LIKE ? ESCAPE '\\')")
            args += [f"%{escaped}%"] * 2
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

    def topics(self, course_id):
        return [r["topic"] for r in self._all(
            "SELECT DISTINCT topic FROM notes WHERE course_id IS ? AND topic != ''", course_id)]

    def rename_topic(self, course_id, old, new):
        # Leaves `updated` alone: refiling isn't editing.
        with self._conn:
            return self._conn.execute(
                "UPDATE notes SET topic = ? WHERE course_id IS ? AND topic = ?",
                (new, course_id, old)).rowcount

    @staticmethod
    def _updated(n: Note) -> str:
        return (n.updated or datetime.now()).isoformat(timespec="seconds")

    def add(self, n: Note) -> int:
        return self._write(
            "INSERT INTO notes (title, body, course_id, pinned, updated, topic)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            n.title, n.body, n.course_id, int(n.pinned), self._updated(n), n.topic)

    def update(self, n: Note):
        self._write(
            "UPDATE notes SET title = ?, body = ?, course_id = ?, pinned = ?, updated = ?,"
            " topic = ? WHERE id = ?",
            n.title, n.body, n.course_id, int(n.pinned), self._updated(n), n.topic, n.id)

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


class SqliteSchoolRecordRepository(_Repo):
    @staticmethod
    def _grade(r) -> Grade:
        return Grade(r["external_id"], r["subject"], date.fromisoformat(r["day"]), r["display"],
                     r["value"], r["component"], r["period"], r["notes"], bool(r["cancelled"]),
                     r["course_id"])

    @staticmethod
    def _lesson(r) -> Lesson:
        return Lesson(r["external_id"], date.fromisoformat(r["day"]), r["subject"], r["topic"],
                      r["teacher"], r["hour"], r["course_id"])

    def grades(self):
        return [self._grade(r) for r in self._all("SELECT * FROM grades ORDER BY day DESC")]

    def replace_grades(self, grades):
        with self._conn:
            self._conn.execute("DELETE FROM grades")
            self._conn.executemany(
                "INSERT OR REPLACE INTO grades (external_id, subject, day, display, value,"
                " component, period, notes, cancelled, course_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(g.external_id, g.subject, g.day.isoformat(), g.display, g.value, g.component,
                  g.period, g.notes, int(g.cancelled), g.course_id) for g in grades])

    def lessons_between(self, first, last):
        return [self._lesson(r) for r in self._all(
            "SELECT * FROM lessons WHERE day BETWEEN ? AND ? ORDER BY day, hour",
            first.isoformat(), last.isoformat())]

    def replace_lessons(self, first, last, lessons):
        with self._conn:
            self._conn.execute("DELETE FROM lessons WHERE day BETWEEN ? AND ?",
                               (first.isoformat(), last.isoformat()))
            self._conn.executemany(
                "INSERT OR REPLACE INTO lessons (external_id, day, subject, topic, teacher, hour,"
                " course_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(l.external_id, l.day.isoformat(), l.subject, l.topic, l.teacher, l.hour,
                  l.course_id) for l in lessons])


    def subjects(self):
        return [Subject(r["external_id"], r["name"],
                        tuple(t for t in r["teachers"].split("\n") if t))
                for r in self._all("SELECT * FROM register_subjects ORDER BY name COLLATE NOCASE")]

    def replace_subjects(self, subjects):
        with self._conn:
            self._conn.execute("DELETE FROM register_subjects")
            self._conn.executemany(
                "INSERT OR REPLACE INTO register_subjects (external_id, name, teachers)"
                " VALUES (?, ?, ?)",
                [(s.external_id, s.name, "\n".join(s.teachers)) for s in subjects])


class SqliteKeyValueStore(_Repo):
    def get(self, key):
        r = self._one("SELECT value FROM settings WHERE key = ?", key)
        return r["value"] if r else None

    def set(self, key, value):
        if value is None:
            self._write("DELETE FROM settings WHERE key = ?", key)
        else:
            self._write("INSERT INTO settings (key, value) VALUES (?, ?)"
                        " ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, value)
