package io.github.quezka.quire.domain

import java.time.LocalDate
import kotlin.math.ceil
import kotlin.math.roundToInt

/**
 * The school register (Classeviva), as on the desktop (domain/register.py). Grades, lesson
 * topics and absences stay on the device that fetched them; they aren't synced.
 */

const val PASS_MARK = 6.0
const val ABSENCE_LIMIT = 0.25
const val SCHOOL_WEEKS = 33 // when the register has no calendar
const val MAX_LESSON_HOUR = 10

data class Grade(
    val id: String,
    val subject: String,
    val day: LocalDate,
    val display: String,
    val value: Double?,
    val component: String = "",
    val period: String = "",
    val notes: String = "",
    val cancelled: Boolean = false,
) {
    val counts get() = value != null && !cancelled
}

fun average(grades: List<Grade>): Double? {
    val values = grades.filter { it.counts }.mapNotNull { it.value }
    return if (values.isEmpty()) null else round2(values.average())
}

/** The mark needed on each of the next [tests] tests for the average to reach [target],
 *  rounded up to a quarter (marks go 6+, 6½, 7-…). */
fun neededGrade(values: List<Double>, target: Double, tests: Int = 1): Double {
    val needed = (target * (values.size + tests) - values.sum()) / tests
    return ceil(needed * 4 - 1e-9) / 4
}

/** Italian marks: 7.5 -> "7½", 6.25 -> "6+", 6.75 -> "7-". */
fun formatMark(value: Double): String {
    val quarters = (value * 4).roundToInt()
    val whole = quarters / 4
    return when (quarters % 4) {
        1 -> "$whole+"
        2 -> "$whole½"
        3 -> "${whole + 1}-"
        else -> "$whole"
    }
}

data class Lesson(
    val id: String,
    val day: LocalDate,
    val subject: String,
    val topic: String,
    val teacher: String = "",
    val hour: Int = 0,
)

enum class AbsenceKind(val code: String) {
    ABSENT("absent"), LATE("late"), SHORT_LATE("short_late"), EARLY_EXIT("early_exit");

    companion object {
        fun of(code: String?) = entries.firstOrNull { it.code == code }
    }
}

data class Absence(
    val id: String,
    val day: LocalDate,
    val kind: AbsenceKind,
    val hour: Int? = null, // the lesson hour of a late entry or early exit, from the register
    val justified: Boolean = false,
    val reason: String = "",
    val hours: Int = 0, // hours the register itself counted (0: unknown)
    val ownHour: Int? = null, // entered here, when the school recorded no hour
) {
    val knownHour get() = hour ?: ownHour
    val hourIsYours get() = hour == null && ownHour != null

    /** A late entry or early exit the register gave no hour for. */
    val needsHour get() = (kind == AbsenceKind.LATE || kind == AbsenceKind.EARLY_EXIT) && hour == null

    fun hoursMissed(hoursThatDay: Int): Int = when {
        hours > 0 -> hours
        kind == AbsenceKind.ABSENT -> hoursThatDay
        kind == AbsenceKind.LATE -> maxOf((knownHour ?: 2) - 1, 0)
        kind == AbsenceKind.EARLY_EXIT -> maxOf(hoursThatDay - (knownHour ?: hoursThatDay) + 1, 0)
        else -> 0
    }
}

data class Notice(
    val id: String,
    val title: String,
    val category: String,
    val published: LocalDate,
    val read: Boolean,
)

data class Subject(val id: String, val name: String, val teachers: List<String>)

/** Everything the phone keeps from the register. */
data class RegisterData(
    val student: String = "",
    val grades: List<Grade> = emptyList(),
    val lessons: List<Lesson> = emptyList(),
    val absences: List<Absence> = emptyList(),
    val notices: List<Notice> = emptyList(),
    val subjects: List<Subject> = emptyList(),
    val schoolDays: List<LocalDate> = emptyList(),
    val lastSync: String? = null,
)

/** Italian "ore" in a class period: 50-60 minutes is one, a double period two. */
fun lessonHours(minutes: Int) = if (minutes > 0) maxOf(1, (minutes / 60.0).roundToInt()) else 0

data class AbsenceSummary(
    val absentDays: Int,
    val lateEntries: Int,
    val earlyExits: Int,
    val unjustified: Int,
    val hoursMissed: Int,
    val schoolHours: Int,
    val limitHours: Int,
) {
    val share get() = if (schoolHours > 0) hoursMissed.toDouble() / schoolHours else null
    val hoursLeft get() = maxOf(limitHours - hoursMissed, 0)
}

object School {
    fun hoursPerWeekday(courses: List<Course>): Map<Int, Int> = courses.flatMap { it.slots }
        .groupBy { it.weekday }.mapValues { (_, slots) -> slots.sumOf { lessonHours(it.end - it.start) } }

    fun absenceSummary(data: RegisterData, courses: List<Course>): AbsenceSummary {
        val perDay = hoursPerWeekday(courses)
        val schoolHours = if (data.schoolDays.isNotEmpty())
            data.schoolDays.sumOf { perDay[it.weekdayIndex()] ?: 0 }
        else perDay.values.sum() * SCHOOL_WEEKS
        val a = data.absences
        return AbsenceSummary(
            a.count { it.kind == AbsenceKind.ABSENT },
            a.count { it.kind == AbsenceKind.LATE || it.kind == AbsenceKind.SHORT_LATE },
            a.count { it.kind == AbsenceKind.EARLY_EXIT },
            a.count { !it.justified },
            a.sumOf { it.hoursMissed(perDay[it.day.weekdayIndex()] ?: 0) },
            schoolHours, (schoolHours * ABSENCE_LIMIT).toInt(),
        )
    }

    /** Registers shout ("MATEMATICA"): sentence case. */
    fun tidySubject(name: String): String {
        val clean = name.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        return if (clean.isNotEmpty() && clean == clean.uppercase() && clean.any { it.isLetter() })
            clean.lowercase().replaceFirstChar { it.uppercase() } else clean
    }

    fun tidyPerson(name: String): String {
        val clean = name.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        return if (clean.isNotEmpty() && clean == clean.uppercase() && clean.any { it.isLetter() })
            clean.lowercase().split(" ").joinToString(" ") { w -> w.replaceFirstChar { it.uppercase() } }
        else clean
    }
}
