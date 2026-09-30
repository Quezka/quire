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


def test_v8_rows_get_sync_ids_and_are_sent_once(tmp_path):
    path = tmp_path / "v8.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'task', course_id INTEGER, due TEXT,
                done INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL DEFAULT '',
                external_id TEXT);
            INSERT INTO tasks (title) VALUES ('Mine');
            INSERT INTO tasks (title, external_id) VALUES ('Imported', 'classeviva:homework:1');
            CREATE TABLE journal (day TEXT PRIMARY KEY, body TEXT NOT NULL DEFAULT '');
            INSERT INTO journal VALUES ('2026-09-01', 'First day');
        """)
    db = SqliteDatabase(path)
    rows = {r["title"]: r for r in db.conn.execute("SELECT * FROM tasks")}
    assert len(rows["Mine"]["uid"]) == 32 and rows["Mine"]["dirty"] == 1
    assert rows["Imported"]["uid"] == "ext:classeviva:homework:1"
    assert db.conn.execute("SELECT uid FROM journal").fetchone()[0] == "day:2026-09-01"
    uid = rows["Mine"]["uid"]
    db.close()

    again = SqliteDatabase(path)  # upgrading twice changes nothing
    assert again.conn.execute("SELECT uid FROM tasks WHERE title = 'Mine'").fetchone()[0] == uid
    again.close()


def test_v10_focus_sessions_count_as_complete(tmp_path):
    path = tmp_path / "v10.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE focus_sessions (id INTEGER PRIMARY KEY, started TEXT NOT NULL,
                                         minutes INTEGER NOT NULL, task_id INTEGER,
                                         label TEXT NOT NULL DEFAULT '');
            INSERT INTO focus_sessions (started, minutes) VALUES ('2026-09-23T10:00:00', 25);
            PRAGMA user_version = 10;
        """)
    db = SqliteDatabase(path)
    assert db.conn.execute("SELECT complete FROM focus_sessions").fetchone()["complete"] == 1
    db.close()


def test_v11_databases_gain_pictures_for_notes(tmp_path):
    path = tmp_path / "v11.db"
    SqliteDatabase(path).close()
    with sqlite3.connect(path) as conn:
        conn.executescript("DROP TABLE note_images; PRAGMA user_version = 11;")
    db = SqliteDatabase(path)
    db.conn.execute("INSERT INTO note_images (uid, mime, data) VALUES ('ab12', 'image/png', x'00')")
    row = db.conn.execute("SELECT uid, dirty FROM note_images").fetchone()
    assert tuple(row) == ("ab12", 1)  # tracked for sync, with the uid it was given
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.close()


def test_v12_databases_gain_notebooks(tmp_path):
    path = tmp_path / "v12.db"
    SqliteDatabase(path).close()
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            DROP TABLE notebooks;
            ALTER TABLE notes DROP COLUMN notebook_id;
            INSERT INTO notes (title, body, updated) VALUES ('Old', '# Old', '2026-01-01T10:00:00');
            PRAGMA user_version = 12;
        """)
    db = SqliteDatabase(path)
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    note = db.conn.execute("SELECT title, notebook_id FROM notes").fetchone()
    assert tuple(note) == ("Old", None)  # kept, filed in no notebook
    db.conn.execute("INSERT INTO notebooks (name) VALUES ('Ideas')")
    row = db.conn.execute("SELECT name, color, dirty FROM notebooks").fetchone()
    assert tuple(row) == ("Ideas", "#8a8f98", 1)  # tracked for sync from the start
    db.conn.execute("UPDATE notes SET notebook_id = 1")
    db.conn.execute("DELETE FROM notebooks")  # deleting a notebook unfiles its notes
    assert db.conn.execute("SELECT notebook_id FROM notes").fetchone()[0] is None
    db.close()
