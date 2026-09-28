package io.github.quezka.quire.data

import io.github.quezka.quire.domain.Agenda
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.DayAgenda
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Note
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.normalizeTopic
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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

    private fun changed(local: Boolean = true) {
        _version.value += 1
        if (local) onLocalChange()
    }

    /** After a sync or a reset: redraw, but it's not a new local edit. */
    fun refreshed() = changed(local = false)

    fun today(): LocalDate = today.invoke()

    // ---- reading ----

    fun courses(): List<Course> = records.live("course").map(Codec::course)
        .sortedBy { it.name.lowercase() }

    fun events(): List<Event> = records.live("event").mapNotNull(Codec::event)
    fun tasks(): List<Task> = records.live("task").map(Codec::task)
    fun task(uid: String): Task? = records.get("task", uid)?.let(Codec::task)
    fun notes(): List<Note> = records.live("note").map(Codec::note)
        .sortedWith(compareByDescending<Note> { it.pinned }.thenByDescending { it.updated })
    fun note(uid: String): Note? = records.get("note", uid)?.let(Codec::note)
    fun jobs(): List<Job> = records.live("job").map(Codec::job)
    fun shifts(): List<Shift> = records.live("shift").mapNotNull(Codec::shift)
    fun journal(day: LocalDate): String = Codec.journalBody(records.get("journal", Codec.journalUid(day)))

    fun day(day: LocalDate): DayAgenda {
        val items = Agenda.itemsOn(day, courses(), events(), jobs(), shifts())
        return DayAgenda(day, items, Agenda.tasksFor(day, today(), tasks()), journal(day))
    }

    // ---- writing ----

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
        records.delete("task", uid)
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

    fun pending() = records.pending()
}
