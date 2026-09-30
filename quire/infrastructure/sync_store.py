"""This device's side of sync, in SQLite.

Change tracking is done by triggers, so the repositories don't know sync exists:
- every synced table has `uid` (the same on every device), `modified` (UTC, ms) and `dirty`;
- inserting, updating or deleting a row (or one of its child rows, like a course's class
  times) marks it dirty and stamps `modified`; deletions leave a tombstone;
- while remote changes are being applied, a row in `sync_flags` switches the triggers off.

Records travel as plain dicts that name related records by uid, never by local row id.
"""
from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from ..application.ports import SyncRecord

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
RANDOM_UID = "lower(hex(randomblob(16)))"


@dataclass(frozen=True)
class Synced:
    kind: str
    table: str
    uid: str  # SQL for a new row's uid, in terms of NEW.<column>
    children: tuple[tuple[str, str], ...] = ()  # (child table, column pointing at the parent)


# Parents before children, so references resolve when a batch is applied in this order.
SYNCED = (
    # Things imported from the school register get the same uid on every device, so two
    # devices importing the same homework don't end up with two copies.
    Synced("course", "courses",
           f"CASE WHEN NEW.external_id IS NOT NULL THEN 'ext:' || NEW.external_id"
           f" ELSE {RANDOM_UID} END", (("class_slots", "course_id"),)),
    Synced("job", "jobs", RANDOM_UID, (("shift_patterns", "job_id"), ("shift_skips", "job_id"))),
    Synced("event", "events", RANDOM_UID),
    Synced("task", "tasks",
           f"CASE WHEN NEW.external_id IS NOT NULL THEN 'ext:' || NEW.external_id"
           f" ELSE {RANDOM_UID} END"),
    Synced("image", "note_images", RANDOM_UID),  # pictures in notes, before the notes
    Synced("note", "notes", RANDOM_UID),
    Synced("journal", "journal", "'day:' || NEW.day"),
    Synced("shift", "shifts", RANDOM_UID),
    Synced("focus", "focus_sessions", RANDOM_UID),
)
BY_KIND = {s.kind: s for s in SYNCED}
ORDER = {s.kind: i for i, s in enumerate(SYNCED)}
NOT_APPLYING = "NOT EXISTS (SELECT 1 FROM sync_flags WHERE name = 'applying')"


def install(conn: sqlite3.Connection) -> None:
    """Schema v9: sync columns, tombstones and triggers (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_flags (name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS sync_tombstones (
            kind TEXT NOT NULL, uid TEXT NOT NULL, modified TEXT NOT NULL,
            dirty INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (kind, uid));
        CREATE TABLE IF NOT EXISTS sync_inbox (
            kind TEXT NOT NULL, uid TEXT NOT NULL, record TEXT NOT NULL,
            PRIMARY KEY (kind, uid));
    """)
    conn.execute("DELETE FROM sync_flags")  # a crash mid-apply mustn't leave tracking off
    for s in SYNCED:
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({s.table})")}
        for column, definition in (("uid", "TEXT"), ("modified", "TEXT"),
                                   ("dirty", "INTEGER NOT NULL DEFAULT 0")):
            if column not in columns:
                conn.execute(f"ALTER TABLE {s.table} ADD COLUMN {column} {definition}")
        # Rows from before sync existed: give them ids and send them the first time.
        backfill = s.uid.replace("NEW.", "")
        conn.execute(f"UPDATE {s.table} SET uid = {backfill}, modified = {NOW}, dirty = 1"
                     " WHERE uid IS NULL")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{s.table}_uid ON {s.table}(uid)")
        conn.executescript(f"""
            CREATE TRIGGER IF NOT EXISTS sync_{s.table}_ins AFTER INSERT ON {s.table}
            WHEN {NOT_APPLYING} BEGIN
                UPDATE {s.table} SET uid = COALESCE(NEW.uid, {s.uid}), modified = {NOW},
                    dirty = 1 WHERE rowid = NEW.rowid;
                DELETE FROM sync_tombstones WHERE kind = '{s.kind}'
                    AND uid = (SELECT uid FROM {s.table} WHERE rowid = NEW.rowid);
            END;
            CREATE TRIGGER IF NOT EXISTS sync_{s.table}_upd AFTER UPDATE ON {s.table}
            WHEN {NOT_APPLYING} BEGIN
                UPDATE {s.table} SET modified = {NOW}, dirty = 1 WHERE rowid = NEW.rowid;
            END;
            CREATE TRIGGER IF NOT EXISTS sync_{s.table}_del AFTER DELETE ON {s.table}
            WHEN {NOT_APPLYING} AND OLD.uid IS NOT NULL BEGIN
                INSERT OR REPLACE INTO sync_tombstones (kind, uid, modified, dirty)
                VALUES ('{s.kind}', OLD.uid, {NOW}, 1);
            END;
        """)
        for child, fk in s.children:
            for event, row in (("INSERT", "NEW"), ("UPDATE", "NEW"), ("DELETE", "OLD")):
                conn.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS sync_{child}_{event.lower()}
                    AFTER {event} ON {child} WHEN {NOT_APPLYING} BEGIN
                        UPDATE {s.table} SET modified = {NOW}, dirty = 1
                        WHERE id = {row}.{fk};
                    END""")


def _dump(record: SyncRecord) -> str:
    return json.dumps({"kind": record.kind, "uid": record.uid, "modified": record.modified,
                       "deleted": record.deleted, "data": record.data})


def _load(text: str) -> SyncRecord:
    raw = json.loads(text)
    return SyncRecord(raw["kind"], raw["uid"], raw["modified"], raw["deleted"], raw["data"])


class SqliteSyncStore:
    def __init__(self, db):
        self._conn: sqlite3.Connection = db.conn

    @contextmanager
    def _applying(self):
        """One transaction with change tracking off (so applied changes aren't echoed)."""
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO sync_flags VALUES ('applying')")
            try:
                yield self._conn
            finally:
                self._conn.execute("DELETE FROM sync_flags WHERE name = 'applying'")

    # ---- uid <-> local id ------------------------------------------------------

    def _uid(self, table: str, row_id) -> str | None:
        if row_id is None:
            return None
        r = self._conn.execute(f"SELECT uid FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return r[0] if r else None

    def _id(self, table: str, uid) -> int | None:
        if uid is None:
            return None
        r = self._conn.execute(f"SELECT id FROM {table} WHERE uid = ?", (uid,)).fetchone()
        return r[0] if r else None

    # ---- outgoing ----------------------------------------------------------------

    def outgoing(self) -> list[SyncRecord]:
        records = []
        for s in SYNCED:
            for row in self._conn.execute(f"SELECT * FROM {s.table} WHERE dirty = 1"):
                records.append(SyncRecord(s.kind, row["uid"], row["modified"], False,
                                          self._export(s.kind, row)))
        for row in self._conn.execute("SELECT * FROM sync_tombstones WHERE dirty = 1"):
            records.append(SyncRecord(row["kind"], row["uid"], row["modified"], True, None))
        return records

    def _export(self, kind: str, r) -> dict:
        q = self._conn.execute
        if kind == "course":
            slots = q("SELECT weekday, start_min, end_min, room FROM class_slots"
                      " WHERE course_id = ? ORDER BY weekday, start_min", (r["id"],))
            return {"name": r["name"], "teacher": r["teacher"], "room": r["room"],
                    "color": r["color"], "external_id": r["external_id"],
                    "slots": [list(s) for s in slots]}
        if kind == "job":
            patterns = q("SELECT weekday, start_min, duration_min, break_min, since, until"
                         " FROM shift_patterns WHERE job_id = ? ORDER BY weekday, start_min",
                         (r["id"],))
            skips = q("SELECT day, start_min FROM shift_skips WHERE job_id = ?", (r["id"],))
            return {"name": r["name"], "color": r["color"], "hourly_rate": r["hourly_rate"],
                    "deductions": r["deductions"], "patterns": [list(p) for p in patterns],
                    "skips": [list(s) for s in skips]}
        if kind == "event":
            return {"day": r["day"], "start": r["start_min"], "end": r["end_min"],
                    "title": r["title"], "details": r["details"], "color": r["color"]}
        if kind == "task":
            return {"title": r["title"], "kind": r["kind"],
                    "course": self._uid("courses", r["course_id"]), "due": r["due"],
                    "done": bool(r["done"]), "details": r["details"],
                    "external_id": r["external_id"]}
        if kind == "note":
            return {"title": r["title"], "body": r["body"],
                    "course": self._uid("courses", r["course_id"]), "pinned": bool(r["pinned"]),
                    "updated": r["updated"], "topic": r["topic"]}
        if kind == "image":
            return {"mime": r["mime"], "data": base64.b64encode(bytes(r["data"])).decode()}
        if kind == "journal":
            return {"day": r["day"], "body": r["body"]}
        if kind == "shift":
            return {"job": self._uid("jobs", r["job_id"]), "day": r["day"],
                    "start": r["start_min"], "duration": r["duration_min"],
                    "break": r["break_min"], "notes": r["notes"]}
        if kind == "focus":
            return {"started": r["started"], "minutes": r["minutes"],
                    "task": self._uid("tasks", r["task_id"]), "label": r["label"],
                    "complete": bool(r["complete"])}
        raise ValueError(kind)

    # ---- incoming ----------------------------------------------------------------

    def _local_modified(self, s: Synced, uid: str) -> str | None:
        row = self._conn.execute(f"SELECT modified FROM {s.table} WHERE uid = ?",
                                 (uid,)).fetchone()
        if row is None:
            row = self._conn.execute("SELECT modified FROM sync_tombstones"
                                     " WHERE kind = ? AND uid = ?", (s.kind, uid)).fetchone()
        return row[0] if row else None

    def apply(self, records: list[SyncRecord]) -> set[tuple[str, str]]:
        changed: set[tuple[str, str]] = set()
        with self._applying() as conn:
            waiting = [_load(r[0]) for r in conn.execute("SELECT record FROM sync_inbox")]
            conn.execute("DELETE FROM sync_inbox")
            # Newest version of each record only, parents first.
            latest: dict[tuple[str, str], SyncRecord] = {}
            for record in [*waiting, *records]:
                if record.kind in BY_KIND:
                    known = latest.get(record.key)
                    if known is None or record.modified > known.modified:
                        latest[record.key] = record
            for record in sorted(latest.values(), key=lambda r: ORDER[r.kind]):
                s = BY_KIND[record.kind]
                local = self._local_modified(s, record.uid)
                if local is not None and local >= record.modified:
                    continue  # ours is as new or newer: it wins (and gets sent if dirty)
                if record.deleted:
                    conn.execute(f"DELETE FROM {s.table} WHERE uid = ?", (record.uid,))
                    conn.execute("INSERT OR REPLACE INTO sync_tombstones VALUES (?, ?, ?, 0)",
                                 (record.kind, record.uid, record.modified))
                    changed.add(record.key)
                elif self._upsert(s, record):
                    conn.execute("DELETE FROM sync_tombstones WHERE kind = ? AND uid = ?",
                                 (record.kind, record.uid))
                    changed.add(record.key)
                else:
                    conn.execute("INSERT OR REPLACE INTO sync_inbox VALUES (?, ?, ?)",
                                 (record.kind, record.uid, _dump(record)))
        return changed

    def _upsert(self, s: Synced, record: SyncRecord) -> bool:
        """Write one record; False if a record it belongs to hasn't arrived yet."""
        d, q = record.data or {}, self._conn.execute
        if s.kind == "course":
            values = {"name": d["name"], "teacher": d.get("teacher", ""), "room": d.get("room", ""),
                      "color": d.get("color", "#4f7cff"), "external_id": d.get("external_id")}
        elif s.kind == "job":
            values = {"name": d["name"], "color": d.get("color", "#0090ff"),
                      "hourly_rate": d.get("hourly_rate"), "deductions": d.get("deductions", 0)}
        elif s.kind == "event":
            values = {"day": d["day"], "start_min": d["start"], "end_min": d["end"],
                      "title": d["title"], "details": d.get("details", ""),
                      "color": d.get("color", "#8a8f98")}
        elif s.kind == "task":
            values = {"title": d["title"], "kind": d.get("kind", "task"),
                      "course_id": self._id("courses", d.get("course")), "due": d.get("due"),
                      "done": int(bool(d.get("done"))), "details": d.get("details", ""),
                      "external_id": d.get("external_id")}
        elif s.kind == "note":
            values = {"title": d.get("title", "Untitled"), "body": d.get("body", ""),
                      "course_id": self._id("courses", d.get("course")),
                      "pinned": int(bool(d.get("pinned"))), "updated": d["updated"],
                      "topic": d.get("topic", "")}
        elif s.kind == "image":
            values = {"mime": d["mime"], "data": base64.b64decode(d["data"])}
        elif s.kind == "journal":
            values = {"day": d["day"], "body": d.get("body", "")}
        elif s.kind == "shift":
            job = self._id("jobs", d.get("job"))
            if job is None:
                return False  # its job comes later
            values = {"job_id": job, "day": d["day"], "start_min": d["start"],
                      "duration_min": d["duration"], "break_min": d.get("break", 0),
                      "notes": d.get("notes", "")}
        elif s.kind == "focus":
            # Older apps don't send "complete": everything they logged was finished.
            values = {"started": d["started"], "minutes": d["minutes"],
                      "task_id": self._id("tasks", d.get("task")), "label": d.get("label", ""),
                      "complete": int(d.get("complete", True))}
        else:
            raise ValueError(s.kind)

        values.update(uid=record.uid, modified=record.modified, dirty=0)
        row = q(f"SELECT rowid FROM {s.table} WHERE uid = ?", (record.uid,)).fetchone()
        if row is None:
            row = self._same_thing(s, values)
        if row is None:
            cols = ", ".join(values)
            q(f"INSERT INTO {s.table} ({cols}) VALUES ({', '.join('?' * len(values))})",
              tuple(values.values()))
            rowid = q("SELECT last_insert_rowid()").fetchone()[0]
        else:
            rowid = row[0]
            q(f"UPDATE {s.table} SET {', '.join(f'{c} = ?' for c in values)} WHERE rowid = ?",
              (*values.values(), rowid))
        if s.kind == "course":
            q("DELETE FROM class_slots WHERE course_id = ?", (rowid,))
            q_many = self._conn.executemany
            q_many("INSERT INTO class_slots (course_id, weekday, start_min, end_min, room)"
                   " VALUES (?, ?, ?, ?, ?)", [(rowid, *slot) for slot in d.get("slots", [])])
        elif s.kind == "job":
            q("DELETE FROM shift_patterns WHERE job_id = ?", (rowid,))
            self._conn.executemany(
                "INSERT INTO shift_patterns (job_id, weekday, start_min, duration_min, break_min,"
                " since, until) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(rowid, *p) for p in d.get("patterns", [])])
            q("DELETE FROM shift_skips WHERE job_id = ?", (rowid,))
            self._conn.executemany(
                "INSERT OR IGNORE INTO shift_skips (job_id, day, start_min) VALUES (?, ?, ?)",
                [(rowid, *k) for k in d.get("skips", [])])
        return True

    def _same_thing(self, s: Synced, values: dict):
        """A local row that is the same thing under another uid: the same day's journal, or
        the same register item imported before this device had synced."""
        if s.kind == "journal":
            return self._conn.execute("SELECT rowid FROM journal WHERE day = ?",
                                      (values["day"],)).fetchone()
        if s.kind in ("task", "course") and values.get("external_id"):
            return self._conn.execute(f"SELECT rowid FROM {s.table} WHERE external_id = ?",
                                      (values["external_id"],)).fetchone()
        return None

    # ---- bookkeeping -------------------------------------------------------------

    def mark_sent(self, records: list[SyncRecord]) -> None:
        with self._applying() as conn:
            for r in records:
                if r.deleted:
                    conn.execute("UPDATE sync_tombstones SET dirty = 0"
                                 " WHERE kind = ? AND uid = ? AND modified = ?",
                                 (r.kind, r.uid, r.modified))
                elif r.kind in BY_KIND:
                    conn.execute(f"UPDATE {BY_KIND[r.kind].table} SET dirty = 0"
                                 " WHERE uid = ? AND modified = ?", (r.uid, r.modified))

    def pending(self) -> int:
        total = self._conn.execute("SELECT COUNT(*) FROM sync_tombstones WHERE dirty = 1"
                                   ).fetchone()[0]
        for s in SYNCED:
            total += self._conn.execute(f"SELECT COUNT(*) FROM {s.table} WHERE dirty = 1"
                                        ).fetchone()[0]
        return total

    def clear_all(self) -> None:
        with self._applying() as conn:
            for s in reversed(SYNCED):
                conn.execute(f"DELETE FROM {s.table}")
            conn.execute("DELETE FROM sync_tombstones")
            conn.execute("DELETE FROM sync_inbox")
