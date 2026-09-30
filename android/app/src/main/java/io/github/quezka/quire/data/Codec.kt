package io.github.quezka.quire.data

import io.github.quezka.quire.domain.ClassSlot
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.FocusSession
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Note
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.TaskKind
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import java.time.LocalDate
import java.time.LocalDateTime
import java.util.UUID

/**
 * Records <-> things, in the desktop's payload format (infrastructure/sync_store.py
 * `_export`/`_upsert`). Fields this app doesn't use are carried over untouched when saving,
 * so editing on the phone never drops something the desktop knows about.
 */
object Codec {
    fun newUid(): String = UUID.randomUUID().toString().replace("-", "")
    fun journalUid(day: LocalDate) = "day:$day"

    private fun JsonObject.str(key: String, default: String = ""): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: default

    private fun JsonObject.strOrNull(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.int(key: String, default: Int = 0) =
        (this[key] as? JsonPrimitive)?.intOrNull ?: default

    private fun JsonObject.bool(key: String) = (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

    private fun JsonObject.double(key: String) = (this[key] as? JsonPrimitive)?.doubleOrNull

    private fun JsonObject.list(key: String): List<JsonArray> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonArray } ?: emptyList()

    private fun JsonArray.s(i: Int): String? = (getOrNull(i) as? JsonPrimitive)?.takeIf { it.isString }?.content
    private fun JsonArray.i(i: Int): Int = (getOrNull(i) as? JsonPrimitive)?.intOrNull ?: 0

    private fun date(text: String?): LocalDate? = text?.takeIf { it.isNotBlank() }?.let {
        runCatching { LocalDate.parse(it.take(10)) }.getOrNull()
    }

    /** Keep what we don't know about from the stored payload, then write our fields. */
    private fun merged(previous: JsonObject?, fields: Map<String, JsonElement>) =
        JsonObject((previous ?: JsonObject(emptyMap())) + fields)

    private fun text(value: String?): JsonElement = value?.let(::JsonPrimitive) ?: JsonNull

    // ---- courses ----

    fun course(r: SyncRecord): Course {
        val d = r.data!!
        return Course(r.uid, d.str("name"), d.str("teacher"), d.str("room"),
            d.str("color", "#4f7cff"),
            d.list("slots").map { ClassSlot(it.i(0), it.i(1), it.i(2), it.s(3) ?: "") },
            d.strOrNull("external_id"))
    }

    fun courseData(c: Course, previous: JsonObject?) = merged(previous, mapOf(
        "name" to JsonPrimitive(c.name), "teacher" to JsonPrimitive(c.teacher),
        "room" to JsonPrimitive(c.room), "color" to JsonPrimitive(c.color),
        "external_id" to text(c.externalId),
        "slots" to buildJsonArray {
            for (s in c.slots) add(buildJsonArray {
                add(JsonPrimitive(s.weekday)); add(JsonPrimitive(s.start)); add(JsonPrimitive(s.end))
                add(JsonPrimitive(s.room))
            })
        },
    ))

    // ---- events ----

    fun event(r: SyncRecord): Event? {
        val d = r.data!!
        val day = date(d.strOrNull("day")) ?: return null
        return Event(r.uid, day, d.int("start"), d.int("end"), d.str("title"), d.str("details"),
            d.str("color", "#8a8f98"))
    }

    fun eventData(e: Event, previous: JsonObject?) = merged(previous, mapOf(
        "day" to JsonPrimitive(e.day.toString()), "start" to JsonPrimitive(e.start),
        "end" to JsonPrimitive(e.end), "title" to JsonPrimitive(e.title),
        "details" to JsonPrimitive(e.details), "color" to JsonPrimitive(e.color),
    ))

    // ---- tasks ----

    fun task(r: SyncRecord): Task {
        val d = r.data!!
        return Task(r.uid, d.str("title"), TaskKind.of(d.strOrNull("kind")), d.strOrNull("course"),
            date(d.strOrNull("due")), d.bool("done"), d.str("details"), d.strOrNull("external_id"))
    }

    fun taskData(t: Task, previous: JsonObject?) = merged(previous, mapOf(
        "title" to JsonPrimitive(t.title), "kind" to JsonPrimitive(t.kind.code),
        "course" to text(t.courseUid), "due" to text(t.due?.toString()),
        "done" to JsonPrimitive(t.done), "details" to JsonPrimitive(t.details),
        "external_id" to text(t.externalId),
    ))

    // ---- pictures in notes (added on the desktop; the phone shows them) ----

    fun image(r: SyncRecord): ByteArray? = r.data?.let { d ->
        runCatching { java.util.Base64.getDecoder().decode(d.str("data")) }.getOrNull()
    }

    // ---- notes ----

    fun note(r: SyncRecord): Note {
        val d = r.data!!
        return Note(r.uid, d.str("body"), d.strOrNull("course"), d.bool("pinned"), d.str("topic"),
            d.str("updated"))
    }

    fun noteData(n: Note, previous: JsonObject?) = merged(previous, mapOf(
        "title" to JsonPrimitive(n.title), "body" to JsonPrimitive(n.body),
        "course" to text(n.courseUid), "pinned" to JsonPrimitive(n.pinned),
        "updated" to JsonPrimitive(n.updated), "topic" to JsonPrimitive(n.topic),
    ))

    // ---- journal ----

    fun journalBody(r: SyncRecord?): String = r?.data?.str("body") ?: ""

    fun journalData(day: LocalDate, body: String) = buildJsonObject {
        put("day", day.toString()); put("body", body)
    }

    // ---- work ----

    fun job(r: SyncRecord): Job {
        val d = r.data!!
        return Job(r.uid, d.str("name"), d.str("color", "#0090ff"), d.double("hourly_rate"),
            d.double("deductions") ?: 0.0,
            d.list("patterns").map {
                ShiftPattern(it.i(0), it.i(1), it.i(2), it.i(3), date(it.s(4)), date(it.s(5)))
            },
            d.list("skips").mapNotNull { a -> date(a.s(0))?.let { it to a.i(1) } }.toSet())
    }

    fun jobData(j: Job, previous: JsonObject?) = merged(previous, mapOf(
        "name" to JsonPrimitive(j.name), "color" to JsonPrimitive(j.color),
        "hourly_rate" to (j.hourlyRate?.let(::JsonPrimitive) ?: JsonNull),
        "deductions" to JsonPrimitive(j.deductions),
        "patterns" to buildJsonArray {
            for (p in j.patterns.sortedWith(compareBy({ it.weekday }, { it.start }))) add(buildJsonArray {
                add(JsonPrimitive(p.weekday)); add(JsonPrimitive(p.start)); add(JsonPrimitive(p.duration))
                add(JsonPrimitive(p.breakMinutes)); add(text(p.since?.toString())); add(text(p.until?.toString()))
            })
        },
        "skips" to buildJsonArray {
            for ((day, start) in j.skips.sortedWith(compareBy({ it.first }, { it.second }))) add(buildJsonArray {
                add(JsonPrimitive(day.toString())); add(JsonPrimitive(start))
            })
        },
    ))

    fun shiftData(s: Shift, previous: JsonObject?) = merged(previous, mapOf(
        "job" to JsonPrimitive(s.jobUid), "day" to JsonPrimitive(s.day.toString()),
        "start" to JsonPrimitive(s.start), "duration" to JsonPrimitive(s.duration),
        "break" to JsonPrimitive(s.breakMinutes), "notes" to JsonPrimitive(s.notes),
    ))

    // ---- focus sessions ----

    fun focus(r: SyncRecord): FocusSession? {
        val d = r.data!!
        val started = d.strOrNull("started")?.let { runCatching { LocalDateTime.parse(it) }.getOrNull() }
            ?: return null
        // Older apps don't send "complete": everything they logged was finished.
        val complete = (d["complete"] as? JsonPrimitive)?.booleanOrNull ?: true
        return FocusSession(r.uid, started, d.int("minutes"), d.strOrNull("task"), d.str("label"), complete)
    }

    fun focusData(f: FocusSession) = buildJsonObject {
        put("started", f.started.withNano(0).toString().let { if (it.length == 16) "$it:00" else it })
        put("minutes", f.minutes); put("task", text(f.taskUid)); put("label", f.label)
        put("complete", f.complete)
    }

    fun shift(r: SyncRecord): Shift? {
        val d = r.data!!
        val day = date(d.strOrNull("day")) ?: return null
        val job = d.strOrNull("job") ?: return null
        return Shift(r.uid, job, day, d.int("start"), d.int("duration"), d.int("break"),
            d.str("notes"))
    }
}
