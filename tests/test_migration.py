import sqlite3

from quire.infrastructure.sqlite import SCHEMA_VERSION, SqliteDatabase

V1_SCHEMA = """
CREATE TABLE courses (id INTEGER PRIMARY KEY, name TEXT NOT NULL, teacher TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#4f7cff');
CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'task',
    course_id INTEGER, due TEXT, done INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL DEFAULT '');
CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT 'Untitled',
    body TEXT NOT NULL DEFAULT '', course_id INTEGER, pinned INTEGER NOT NULL DEFAULT 0,
    updated TEXT NOT NULL);
INSERT INTO notes (title, body, updated) VALUES ('Old note', '# Old note', '2026-01-01T10:00:00');
INSERT INTO courses (name) VALUES ('Maths');
INSERT INTO tasks (title, course_id) VALUES ('Old task', 1);
PRAGMA user_version = 1;
"""


def test_v1_database_is_upgraded_in_place(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(V1_SCHEMA)

    db = SqliteDatabase(path)
    columns = {r["name"] for r in db.conn.execute("PRAGMA table_info(tasks)")}
    assert "external_id" in columns
    assert db.conn.execute("SELECT title FROM tasks").fetchone()["title"] == "Old task"
    note = db.conn.execute("SELECT title, topic FROM notes").fetchone()
    assert (note["title"], note["topic"]) == ("Old note", "")
    tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"jobs", "shifts", "register_subjects", "grades", "lessons", "settings",
            "shift_patterns", "shift_skips", "focus_sessions"} <= tables
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.close()

    SqliteDatabase(path).close()  # opening twice is a no-op


def test_v7_focus_sessions_gain_a_label(tmp_path):
    path = tmp_path / "v7.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE focus_sessions (id INTEGER PRIMARY KEY, started TEXT NOT NULL,
                                         minutes INTEGER NOT NULL, task_id INTEGER);
            INSERT INTO focus_sessions (started, minutes) VALUES ('2026-09-23T10:00:00', 25);
        """)
    db = SqliteDatabase(path)
    assert db.conn.execute("SELECT label FROM focus_sessions").fetchone()["label"] == ""
    db.close()
