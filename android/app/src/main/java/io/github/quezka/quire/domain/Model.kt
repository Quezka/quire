package io.github.quezka.quire.domain

import java.time.LocalDate

/**
 * The same things the desktop app keeps, with the same meaning. They travel between devices
 * as sync records (see data/Codec.kt); references between them are record uids.
 */

const val MINUTES_PER_DAY = 24 * 60
const val UPCOMING_DAYS = 7
const val TODAY_TASK_DAYS = 14

val COURSE_COLORS = listOf(
    "#4f7cff", "#e5484d", "#30a46c", "#f5a524", "#8e4ec6",
    "#12a594", "#e93d82", "#f76b15", "#0090ff", "#978365",
)

/** Weekdays are numbered like the desktop (Python): Monday = 0 … Sunday = 6. */
fun LocalDate.weekdayIndex(): Int = dayOfWeek.value - 1

data class ClassSlot(val weekday: Int, val start: Int, val end: Int, val room: String = "")

data class Course(
    val uid: String,
    val name: String,
    val teacher: String = "",
    val room: String = "",
    val color: String = COURSE_COLORS[0],
    val slots: List<ClassSlot> = emptyList(),
    val externalId: String? = null,
) {
    fun roomFor(slot: ClassSlot) = slot.room.ifBlank { room }
}

data class Event(
    val uid: String,
    val day: LocalDate,
    val start: Int,
    val end: Int,
    val title: String,
    val details: String = "",
    val color: String = "#8a8f98",
)

enum class TaskKind(val code: String) {
    TASK("task"), HOMEWORK("homework"), ASSIGNMENT("assignment"), EXAM("exam"), READING("reading");

    companion object {
        fun of(code: String?) = entries.firstOrNull { it.code == code } ?: TASK
    }
}

enum class DueBucket { OVERDUE, TODAY, UPCOMING, LATER, UNDATED, DONE }

data class Task(
    val uid: String,
    val title: String,
    val kind: TaskKind = TaskKind.TASK,
    val courseUid: String? = null,
    val due: LocalDate? = null,
    val done: Boolean = false,
    val details: String = "",
    val externalId: String? = null,
) {
    val imported get() = externalId != null

    fun bucket(today: LocalDate): DueBucket = when {
        done -> DueBucket.DONE
        due == null -> DueBucket.UNDATED
        due < today -> DueBucket.OVERDUE
        due == today -> DueBucket.TODAY
        due <= today.plusDays(UPCOMING_DAYS.toLong()) -> DueBucket.UPCOMING
        else -> DueBucket.LATER
    }

    fun isOverdue(today: LocalDate) = !done && due != null && due < today
}

data class Note(
    val uid: String,
    val body: String,
    val courseUid: String? = null,
    val pinned: Boolean = false,
    val topic: String = "",
    val updated: String = "",
    /** A note is in a course or a notebook, not both (a course wins, as on the desktop). */
    val notebookUid: String? = null,
) {
    val title get() = deriveNoteTitle(body)
}

/** A group of notes that isn't a course: Ideas, Trips, a project. */
data class Notebook(
    val uid: String,
    val name: String,
    val color: String = NOTEBOOK_COLOR,
)

const val NOTEBOOK_COLOR = "#8a8f98"

/** A note's title is its first non-empty line, minus markdown heading marks. */
/** A picture in a note, as the desktop writes it: ![alt](quire-image:<uid>). */
val IMAGE_REF = Regex("""!\[([^\]\n]*)\]\(quire-image:([0-9a-f]{8,64})\)""")

/** Text with pictures replaced by their descriptions (for titles and snippets). */
fun withoutImages(text: String) = IMAGE_REF.replace(text) { it.groupValues[1] }

fun deriveNoteTitle(body: String): String {
    for (line in body.lines()) {
        val text = withoutImages(line).trim().trimStart('#').trim()
        if (text.isNotEmpty()) return text.take(120)
    }
    return "Untitled"
}

fun normalizeTopic(text: String) = text.split(Regex("\\s+")).filter { it.isNotEmpty() }
    .joinToString(" ").take(60)

data class ShiftPattern(
    val weekday: Int,
    val start: Int,
    val duration: Int,
    val breakMinutes: Int = 0,
    val since: LocalDate? = null,
    val until: LocalDate? = null,
) {
    fun occursOn(day: LocalDate) = day.weekdayIndex() == weekday &&
        (since == null || day >= since) && (until == null || day <= until)
}

data class Job(
    val uid: String,
    val name: String,
    val color: String = "#0090ff",
    val hourlyRate: Double? = null,
    val deductions: Double = 0.0,
    val patterns: List<ShiftPattern> = emptyList(),
    val skips: Set<Pair<LocalDate, Int>> = emptySet(),
)

data class Shift(
    val uid: String?, // null for an occurrence of a weekly schedule
    val jobUid: String,
    val day: LocalDate,
    val start: Int,
    val duration: Int,
    val breakMinutes: Int = 0,
    val notes: String = "",
) {
    val end get() = start + duration
}
