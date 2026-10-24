package io.github.quezka.quire.domain

import java.time.LocalDateTime

/** One thing on the timeline, with absolute start and end (what a bedside clock counts down to). */
data class BedsideItem(val title: String, val kind: ItemKind, val start: LocalDateTime, val end: LocalDateTime)

/**
 * What a bedside clock (the Vesper app) shows: what is on now or comes next today, what starts the
 * day after, and how many tasks are open. Never grades or anything from the school register.
 */
data class BedsideFeed(
    val now: LocalDateTime,
    val next: BedsideItem?,
    val tomorrowFirst: BedsideItem?,
    val tasksToday: Int,
    val tasksTomorrow: Int,
    val nextTask: Task?,
)

object Bedside {
    fun build(
        now: LocalDateTime,
        courses: List<Course>,
        events: List<Event>,
        jobs: List<Job>,
        shifts: List<Shift>,
        tasks: List<Task>,
        routines: List<Routine> = emptyList(),
    ): BedsideFeed {
        val today = now.toLocalDate()
        val tomorrow = today.plusDays(1)
        val minute = now.hour * 60 + now.minute

        // What is running or still to come today.
        val next = Agenda.itemsOn(today, courses, events, jobs, shifts, routines)
            .filter { it.end > minute }
            .minByOrNull { it.start }
        // The first thing tomorrow; the tail of a shift that started tonight is not a start.
        val first = Agenda.itemsOn(tomorrow, courses, events, jobs, shifts, routines)
            .filter { !it.continues }
            .minByOrNull { it.start }

        val open = tasks.filter { !it.done && it.due != null }
        return BedsideFeed(
            now = now,
            next = next?.let(::item),
            tomorrowFirst = first?.let(::item),
            tasksToday = open.count { it.due!! <= today },
            tasksTomorrow = open.count { it.due == tomorrow },
            nextTask = open.filter { it.due!! <= tomorrow }
                .sortedWith(compareBy({ it.due }, { it.kind != TaskKind.EXAM }, { it.title.lowercase() }))
                .firstOrNull(),
        )
    }

    private fun item(a: AgendaItem): BedsideItem {
        val midnight = a.day.atStartOfDay()
        return BedsideItem(a.title, a.kind, midnight.plusMinutes(a.start.toLong()), midnight.plusMinutes(a.end.toLong()))
    }
}
