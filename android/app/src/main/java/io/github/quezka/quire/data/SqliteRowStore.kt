package io.github.quezka.quire.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

/** Records in a small SQLite table on the phone. */
class SqliteRowStore(context: Context) :
    SQLiteOpenHelper(context, "quire.db", null, 1), RowStore {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE records (
            kind TEXT NOT NULL, uid TEXT NOT NULL, modified TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0, dirty INTEGER NOT NULL DEFAULT 0,
            data TEXT, PRIMARY KEY (kind, uid))""")
        db.execSQL("CREATE INDEX idx_records_dirty ON records(dirty)")
    }

    override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) = Unit

    private fun read(where: String?, args: Array<String>?): List<Row> =
        readableDatabase.query("records", null, where, args, null, null, null).use { c ->
            buildList {
                while (c.moveToNext()) {
                    val data = c.getString(c.getColumnIndexOrThrow("data"))
                    add(Row(SyncRecord(
                        c.getString(c.getColumnIndexOrThrow("kind")),
                        c.getString(c.getColumnIndexOrThrow("uid")),
                        c.getString(c.getColumnIndexOrThrow("modified")),
                        c.getInt(c.getColumnIndexOrThrow("deleted")) == 1,
                        data?.let { Json.parseToJsonElement(it).jsonObject }),
                        c.getInt(c.getColumnIndexOrThrow("dirty")) == 1))
                }
            }
        }

    override fun rows(kind: String?) =
        if (kind == null) read(null, null) else read("kind = ?", arrayOf(kind))

    override fun row(kind: String, uid: String) =
        read("kind = ? AND uid = ?", arrayOf(kind, uid)).firstOrNull()

    override fun put(rows: List<Row>) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            for (row in rows) {
                val r = row.record
                db.insertWithOnConflict("records", null, ContentValues().apply {
                    put("kind", r.kind); put("uid", r.uid); put("modified", r.modified)
                    put("deleted", if (r.deleted) 1 else 0); put("dirty", if (row.dirty) 1 else 0)
                    put("data", r.data?.let { JsonObject(it).toString() })
                }, SQLiteDatabase.CONFLICT_REPLACE)
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    override fun clear() {
        writableDatabase.delete("records", null, null)
    }
}
