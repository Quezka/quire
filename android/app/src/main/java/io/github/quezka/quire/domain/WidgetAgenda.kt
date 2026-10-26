package io.github.quezka.quire.domain

import java.time.LocalDate
import java.time.LocalDateTime

/** One line of the home-screen agenda: a task due that day, or something on the timeline. */
sealed interface WidgetEntry {
    data class Due(val task: Task, val overdue: Boolean) : WidgetEntry
    data class Timed(val item: AgendaItem) : WidgetEntry
}

data class WidgetDay(val day: LocalDate, val entries: List<WidgetEntry>)

/** What the home-screen widget lists: the next days, like the calendar apps' agenda widgets. */
object WidgetAgenda {
    const val DAYS = 7
    const val MAX_ENTRIES = 30

    /** Days from today on that have something, each with tasks first and then the timeline.
     *  Today hides what already ended; overdue tasks sit under today. Days without
     *  anything are left out. */
    fun build(
        now: LocalDateTime,
        courses: List<Course>,
        events: List<Event>,
        jobs: List<Job>,
        shifts: List<Shift>,
        tasks: List<Task>,
        routines: List<Routine> = emptyList(),
    ): List<WidgetDay> {
        val today = now.toLocalDate()
        val minute = now.hour * 60 + now.minute
        val open = tasks.filter { !it.done && it.due != null }
        // Ticked off today: kept on the list, struck through, until the day is over (tap to undo).
        val doneToday = tasks.filter { it.done && it.due == today }
        val result = mutableListOf<WidgetDay>()
        var total = 0
        for (offset in 0L until DAYS) {
            val day = today.plusDays(offset)
            val entries = mutableListOf<WidgetEntry>()
            for (t in open.filter { if (offset == 0L) it.due!! <= day else it.due == day }
                .sortedWith(compareBy({ it.due }, { it.kind != TaskKind.EXAM }, { it.title.lowercase() }))) {
                entries += WidgetEntry.Due(t, overdue = t.due!! < today)
            }
            if (offset == 0L) for (t in doneToday.sortedBy { it.title.lowercase() }) entries += WidgetEntry.Due(t, overdue = false)
            for (item in Agenda.itemsOn(day, courses, events, jobs, shifts, routines)) {
                if (offset == 0L && item.end <= minute) continue
                entries += WidgetEntry.Timed(item)
            }
            if (entries.isEmpty()) continue
            val room = MAX_ENTRIES - total
            if (room <= 0) break
            result += WidgetDay(day, entries.take(room))
            total += minOf(entries.size, room)
        }
        return result
    }
}
