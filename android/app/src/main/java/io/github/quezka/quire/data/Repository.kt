package io.github.quezka.quire.data

import io.github.quezka.quire.domain.Agenda
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.DayAgenda
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.FocusSession
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Note
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.Work
import io.github.quezka.quire.domain.WorkSummary
import io.github.quezka.quire.domain.monday
import io.github.quezka.quire.domain.normalizeTopic
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonPrimitive
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.temporal.ChronoUnit

/**
 * Typed access for the screens. Every change bumps [version], which the UI watches, and
 * calls [onLocalChange] so a sync can follow shortly after.
 */
class Repository(
    private val records: Records,
    private val today: () -> LocalDate = LocalDate::now,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    private val _version = MutableStateFlow(0)
    val version: StateFlow<Int> = _version
    var onLocalChange: () -> Unit = {}
    var onChanged: () -> Unit = {} // any change, local or synced (reminders re-plan)

    private fun changed(local: Boolean = true) {
        _version.value += 1
        if (local) onLocalChange()
        onChanged()
    }

    /** After a sync or a reset: redraw, but it's not a new local edit. */
    fun refreshed() = changed(local = false)

    fun today(): LocalDate = today.invoke()
    fun now(): LocalDateTime = now.invoke()

    // ---- reading ----

    fun courses(): List<Course> = distinctImports(records.live("course")).first.map(Codec::course)
        .sortedBy { it.name.lowercase() }

    /** Courses by uid, including the uid of a duplicate import (see [distinctImports]). */
    fun courseIndex(): Map<String, Course> {
        val (kept, alias) = distinctImports(records.live("course"))
        val byUid = kept.map(Codec::course).associateBy { it.uid }
        return byUid + alias.mapNotNull { (from, to) -> byUid[to]?.let { from to it } }
    }
    fun course(uid: String): Course? = records.get("course", uid)?.let(Codec::course)

    fun events(): List<Event> = records.live("event").mapNotNull(Codec::event)
    fun event(uid: String): Event? = records.get("event", uid)?.let(Codec::event)
    fun tasks(): List<Task> = distinctImports(records.live("task")).first.map(Codec::task)
    fun task(uid: String): Task? = records.get("task", uid)?.let(Codec::task)
    fun notes(): List<Note> = records.live("note").map(Codec::note)
        .sortedWith(compareByDescending<Note> { it.pinned }.thenByDescending { it.updated })
    fun note(uid: String): Note? = records.get("note", uid)?.let(Codec::note)
    fun image(uid: String): ByteArray? = records.get("image", uid)?.takeIf { !it.deleted }?.let(Codec::image)
    fun jobs(): List<Job> = records.live("job").map(Codec::job).sortedBy { it.name.lowercase() }
    fun job(uid: String): Job? = records.get("job", uid)?.let(Codec::job)
    fun shifts(): List<Shift> = records.live("shift").mapNotNull(Codec::shift)
    fun shift(uid: String): Shift? = records.get("shift", uid)?.let(Codec::shift)
    fun focusSessions(): List<FocusSession> = records.live("focus").mapNotNull(Codec::focus)
    fun journal(day: LocalDate): String = Codec.journalBody(records.get("journal", Codec.journalUid(day)))

    fun day(day: LocalDate): DayAgenda {
        val items = Agenda.itemsOn(day, courses(), events(), jobs(), shifts())
        return DayAgenda(day, items, Agenda.tasksFor(day, today(), tasks()), journal(day))
    }

    /** The seven days from [monday], each with its timeline items. */
    fun week(monday: LocalDate): List<Pair<LocalDate, List<AgendaItem>>> {
        val courses = courses(); val events = events(); val jobs = jobs(); val shifts = shifts()
        return (0L..6L).map { monday.plusDays(it) }.map { it to Agenda.itemsOn(it, courses, events, jobs, shifts) }
    }

    fun tasksDue(first: LocalDate, last: LocalDate): List<Task> =
        tasks().filter { t -> t.due != null && t.due in first..last }

    fun workWeek(): WorkSummary = Work.week(jobs(), shifts(), today())
    fun workMonth(): WorkSummary = Work.month(jobs(), shifts(), today())

    // ---- tasks and notes ----

    fun saveTask(task: Task): Task {
        val saved = task.copy(title = task.title.trim().ifEmpty { "Untitled task" })
        records.save("task", saved.uid, Codec.taskData(saved, records.get("task", saved.uid)?.data))
        changed()
        return saved
    }

    fun setDone(uid: String, done: Boolean) {
        task(uid)?.let { saveTask(it.copy(done = done)) }
    }

    fun deleteTask(uid: String) {
        for (same in sameTask(uid)) records.delete("task", same)
        changed()
    }

    fun saveNote(note: Note): Note {
        val saved = note.copy(topic = normalizeTopic(note.topic),
            updated = now().truncatedTo(ChronoUnit.SECONDS).toString())
        records.save("note", saved.uid, Codec.noteData(saved, records.get("note", saved.uid)?.data))
        changed()
        return saved
    }

    fun deleteNote(uid: String) {
        records.delete("note", uid)
        changed()
    }

    /** Like the desktop: an empty day note is deleted rather than kept blank. */
    fun saveJournal(day: LocalDate, body: String) {
        val uid = Codec.journalUid(day)
        if (body.isBlank()) records.delete("journal", uid)
        else records.save("journal", uid, Codec.journalData(day, body))
        changed()
    }

    // ---- events and courses ----

    fun saveEvent(event: Event): Event {
        val saved = event.copy(title = event.title.trim().ifEmpty { "Untitled event" })
        records.save("event", saved.uid, Codec.eventData(saved, records.get("event", saved.uid)?.data))
        changed()
        return saved
    }

    fun deleteEvent(uid: String) {
        records.delete("event", uid)
        changed()
    }

    fun saveCourse(course: Course): Course {
        val saved = course.copy(name = course.name.trim().ifEmpty { "Untitled course" },
            slots = course.slots.sortedWith(compareBy({ it.weekday }, { it.start })))
        records.save("course", saved.uid, Codec.courseData(saved, records.get("course", saved.uid)?.data))
        changed()
        return saved
    }

    /** Delete a course; its tasks and notes stay, without a course (as on the desktop). */
    fun deleteCourse(uid: String) {
        for (t in tasks().filter { it.courseUid == uid }) {
            records.save("task", t.uid, Codec.taskData(t.copy(courseUid = null), records.get("task", t.uid)?.data))
        }
        for (n in notes().filter { it.courseUid == uid }) {
            records.save("note", n.uid, Codec.noteData(n.copy(courseUid = null), records.get("note", n.uid)?.data))
        }
        records.delete("course", uid)
        changed()
    }

    // ---- work ----

    /** Save a job; [weekly] (when given) becomes its schedule from this week on, keeping
     *  the weeks already worked as they were. */
    fun saveJob(job: Job, weekly: List<ShiftPattern>? = null): Job {
        var saved = job.copy(name = job.name.trim().ifEmpty { "Job" })
        if (weekly != null) saved = saved.copy(patterns = Work.reschedule(saved.patterns, weekly, today().monday()))
        records.save("job", saved.uid, Codec.jobData(saved, records.get("job", saved.uid)?.data))
        changed()
        return saved
    }

    /** Delete a job together with all of its shifts. */
    fun deleteJob(uid: String) {
        for (s in shifts().filter { it.jobUid == uid }) s.uid?.let { records.delete("shift", it) }
        records.delete("job", uid)
        changed()
    }

    /** Save a one-off shift, optionally copied to the next [repeatWeeks] weeks. [replaces]
     *  is a weekly occurrence (day, start) this shift stands in for, e.g. a different time
     *  just this week. */
    fun saveShift(shift: Shift, repeatWeeks: Int = 0, replaces: Pair<LocalDate, Int>? = null) {
        val uid = shift.uid ?: Codec.newUid()
        records.save("shift", uid, Codec.shiftData(shift, records.get("shift", uid)?.data))
        for (week in 1..repeatWeeks.coerceIn(0, Work.MAX_REPEAT_WEEKS)) {
            val copy = shift.copy(day = shift.day.plusWeeks(week.toLong()))
            records.save("shift", Codec.newUid(), Codec.shiftData(copy, null))
        }
        if (replaces != null) job(shift.jobUid)?.let { skipIn(it, replaces) }
        changed()
    }

    fun deleteShift(uid: String) {
        records.delete("shift", uid)
        changed()
    }

    /** Take one week's occurrence of a weekly shift off the schedule. */
    fun skipOccurrence(jobUid: String, day: LocalDate, start: Int) {
        job(jobUid)?.let { skipIn(it, day to start) }
        changed()
    }

    private fun skipIn(job: Job, occurrence: Pair<LocalDate, Int>) {
        val updated = job.copy(skips = job.skips + occurrence)
        records.save("job", job.uid, Codec.jobData(updated, records.get("job", job.uid)?.data))
    }

    // ---- focus ----

    fun logFocus(session: FocusSession) {
        records.save("focus", session.uid, Codec.focusData(session))
        changed()
    }

    // ---- register imports ----

    /** A task or course imported from the register by both the phone and the computer
     *  (before they had synced) exists twice, under two uids. The desktop folds them into
     *  one row when they reach it; here the most recently changed one is shown, and
     *  references to the other lead to it. */
    private fun distinctImports(list: List<SyncRecord>): Pair<List<SyncRecord>, Map<String, String>> {
        val alias = mutableMapOf<String, String>()
        val kept = mutableListOf<SyncRecord>()
        val byExternal = list.groupBy { r -> externalId(r) ?: "uid:${r.uid}" }
        for ((_, same) in byExternal) {
            val keep = same.maxWith(compareBy({ it.modified }, { it.uid }))
            kept += keep
            for (other in same) if (other.uid != keep.uid) alias[other.uid] = keep.uid
        }
        return kept to alias
    }

    private fun externalId(r: SyncRecord) =
        (r.data?.get("external_id") as? JsonPrimitive)?.takeIf { it.isString }?.content

    /** Every uid of the same task (normally just [uid]). */
    private fun sameTask(uid: String): List<String> {
        val external = records.get("task", uid)?.let(::externalId) ?: return listOf(uid)
        return records.live("task").filter { externalId(it) == external }.map { it.uid }
    }

    /** Apply a batch of changes made by the register sync as one local change. */
    fun <T> batch(block: Records.() -> T): T {
        val result = records.block()
        changed()
        return result
    }

    fun pending() = records.pending()
}
