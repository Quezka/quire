"""SQLite connection, schema and backup."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    teacher  TEXT NOT NULL DEFAULT '',
    room     TEXT NOT NULL DEFAULT '',
    color    TEXT NOT NULL DEFAULT '#4f7cff',
    external_id TEXT
);
CREATE TABLE IF NOT EXISTS class_slots (
    id        INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    weekday   INTEGER NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL,
    room      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL,
    title     TEXT NOT NULL,
    details   TEXT NOT NULL DEFAULT '',
    color     TEXT NOT NULL DEFAULT '#8a8f98'
);
CREATE TABLE IF NOT EXISTS tasks (
    id        INTEGER PRIMARY KEY,
    title     TEXT NOT NULL,
    kind      TEXT NOT NULL DEFAULT 'task',
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    due       TEXT,
    done      INTEGER NOT NULL DEFAULT 0,
    details   TEXT NOT NULL DEFAULT '',
    external_id TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id        INTEGER PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT 'Untitled',
    body      TEXT NOT NULL DEFAULT '',
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    pinned    INTEGER NOT NULL DEFAULT 0,
    updated   TEXT NOT NULL,
    topic     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS journal (
    day  TEXT PRIMARY KEY,
    body TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grades (
    external_id TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    day         TEXT NOT NULL,
    display     TEXT NOT NULL,
    value       REAL,
    component   TEXT NOT NULL DEFAULT '',
    period      TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    cancelled   INTEGER NOT NULL DEFAULT 0,
    course_id   INTEGER REFERENCES courses(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    external_id TEXT PRIMARY KEY,
    day         TEXT NOT NULL,
    subject     TEXT NOT NULL,
    topic       TEXT NOT NULL DEFAULT '',
    teacher     TEXT NOT NULL DEFAULT '',
    hour        INTEGER NOT NULL DEFAULT 0,
    course_id   INTEGER REFERENCES courses(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS register_subjects (
    external_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    teachers    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#0090ff',
    hourly_rate REAL,
    deductions  REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS shifts (
    id            INTEGER PRIMARY KEY,
    job_id        INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    day           TEXT NOT NULL,
    start_min     INTEGER NOT NULL,
    duration_min  INTEGER NOT NULL,
    break_min     INTEGER NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_shifts_day ON shifts(day);
CREATE TABLE IF NOT EXISTS shift_patterns (
    id           INTEGER PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    weekday      INTEGER NOT NULL,
    start_min    INTEGER NOT NULL,
    duration_min INTEGER NOT NULL,
    break_min    INTEGER NOT NULL DEFAULT 0,
    since        TEXT,
    until        TEXT
);
CREATE TABLE IF NOT EXISTS shift_skips (
    job_id    INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    day       TEXT NOT NULL,
    start_min INTEGER NOT NULL,
    PRIMARY KEY (job_id, day, start_min)
);
CREATE TABLE IF NOT EXISTS focus_sessions (
    id       INTEGER PRIMARY KEY,
    started  TEXT NOT NULL,
    minutes  INTEGER NOT NULL,
    task_id  INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    label    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_focus_started ON focus_sessions(started);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
CREATE INDEX IF NOT EXISTS idx_lessons_day ON lessons(day);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
"""


class SqliteDatabase:
    """Owns the connection. Also implements the application's Storage port."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self):
        """Create missing tables and bring older databases up to SCHEMA_VERSION."""
        self.conn.executescript(SCHEMA)
        # v2: sync ids for records imported from a school register.
        self._add_column("courses", "external_id", "TEXT")
        self._add_column("tasks", "external_id", "TEXT")
        # v4 (register_subjects), v5 (jobs, shifts), v6 (shift_patterns, shift_skips) and
        # v7 (focus_sessions) add tables, which SCHEMA creates.
        # v6: share of pay withheld for tax per job.
        self._add_column("jobs", "deductions", "REAL NOT NULL DEFAULT 0")
        # v8: what a focus session was spent on (task title or ad-hoc project).
        self._add_column("focus_sessions", "label", "TEXT NOT NULL DEFAULT ''")
        # v3: topics group notes within a course.
        self._add_column("notes", "topic", "TEXT NOT NULL DEFAULT ''")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_external"
                          " ON tasks(external_id) WHERE external_id IS NOT NULL")
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def _add_column(self, table: str, column: str, definition: str):
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @property
    def location(self) -> Path:
        return self.path

    def backup_to(self, dest: str | Path):
        with sqlite3.connect(str(dest)) as out:
            self.conn.backup(out)

    def close(self):
        self.conn.close()
