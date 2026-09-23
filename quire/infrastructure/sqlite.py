"""SQLite connection, schema and backup."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    teacher  TEXT NOT NULL DEFAULT '',
    room     TEXT NOT NULL DEFAULT '',
    color    TEXT NOT NULL DEFAULT '#4f7cff'
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
    details   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notes (
    id        INTEGER PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT 'Untitled',
    body      TEXT NOT NULL DEFAULT '',
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    pinned    INTEGER NOT NULL DEFAULT 0,
    updated   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    day  TEXT PRIMARY KEY,
    body TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
"""


class SqliteDatabase:
    """Owns the connection. Also implements the application's Storage port."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    @property
    def location(self) -> Path:
        return self.path

    def backup_to(self, dest: str | Path):
        with sqlite3.connect(str(dest)) as out:
            self.conn.backup(out)

    def close(self):
        self.conn.close()
