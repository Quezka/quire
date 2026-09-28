package io.github.quezka.quire.data

import kotlinx.serialization.json.JsonObject
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/** One synced thing, exactly as it travels (see the desktop's application/ports.py). */
data class SyncRecord(
    val kind: String,
    val uid: String,
    val modified: String, // ISO-8601 UTC with milliseconds; the newer change wins
    val deleted: Boolean = false,
    val data: JsonObject? = null,
) {
    val key get() = kind to uid
}

/** A stored record, plus whether it still has to be sent. */
data class Row(val record: SyncRecord, val dirty: Boolean)

/** Where records live on this device (SQLite in the app, a map in tests). */
interface RowStore {
    fun rows(kind: String? = null): List<Row>
    fun row(kind: String, uid: String): Row?
    fun put(rows: List<Row>)
    fun clear()
}

class MemoryRowStore : RowStore {
    private val map = linkedMapOf<Pair<String, String>, Row>()
    override fun rows(kind: String?) = map.values.filter { kind == null || it.record.kind == kind }
    override fun row(kind: String, uid: String) = map[kind to uid]
    override fun put(rows: List<Row>) = rows.forEach { map[it.record.key] = it }
    override fun clear() = map.clear()
}

private val STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)

fun stamp(instant: Instant): String = STAMP.format(instant)

/**
 * Local-first bookkeeping over a [RowStore]: local edits are stamped and marked to send;
 * records from other devices are taken only where they're newer.
 */
class Records(private val store: RowStore, private val clock: () -> Instant = Instant::now) {

    private fun nextStamp(kind: String, uid: String): String {
        var now = clock()
        val previous = store.row(kind, uid)?.record?.modified
        // Never go back in time for the same record (clock changes, two edits in one ms).
        if (previous != null && stamp(now) <= previous) {
            now = Instant.parse(previous).plusMillis(1)
        }
        return stamp(now)
    }

    fun live(kind: String): List<SyncRecord> =
        store.rows(kind).map { it.record }.filter { !it.deleted && it.data != null }

    fun get(kind: String, uid: String): SyncRecord? =
        store.row(kind, uid)?.record?.takeIf { !it.deleted }

    fun save(kind: String, uid: String, data: JsonObject) {
        store.put(listOf(Row(SyncRecord(kind, uid, nextStamp(kind, uid), false, data), dirty = true)))
    }

    fun delete(kind: String, uid: String) {
        if (store.row(kind, uid) == null) return
        store.put(listOf(Row(SyncRecord(kind, uid, nextStamp(kind, uid), true, null), dirty = true)))
    }

    fun outgoing(): List<SyncRecord> = store.rows().filter { it.dirty }.map { it.record }

    fun pending(): Int = store.rows().count { it.dirty }

    /** Take records from other devices where they're newer than ours; returns those taken. */
    fun apply(incoming: List<SyncRecord>): List<SyncRecord> {
        val newest = linkedMapOf<Pair<String, String>, SyncRecord>()
        for (r in incoming) {
            val known = newest[r.key]
            if (known == null || r.modified > known.modified) newest[r.key] = r
        }
        val taken = newest.values.filter { r ->
            val local = store.row(r.kind, r.uid)?.record
            local == null || local.modified < r.modified
        }
        store.put(taken.map { Row(it, dirty = false) })
        return taken
    }

    /** They reached the cloud: stop sending them, unless they changed again since. */
    fun markSent(sent: List<SyncRecord>) {
        store.put(sent.mapNotNull { r ->
            store.row(r.kind, r.uid)?.takeIf { it.record.modified == r.modified }?.copy(dirty = false)
        })
    }

    fun clear() = store.clear()
}
