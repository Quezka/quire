import sqlite3

from quire.infrastructure.sqlite import SCHEMA_VERSION, SqliteDatabase

V1_SCHEMA = """
CREATE TABLE courses (id INTEGER PRIMARY KEY, name TEXT NOT NULL, teacher TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#4f7cff');
CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'task',
    course_id INTEGER, due TEXT, done INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL DEFAULT '');
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
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.close()

    SqliteDatabase(path).close()  # opening twice is a no-op
