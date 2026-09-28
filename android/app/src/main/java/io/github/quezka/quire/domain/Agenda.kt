package io.github.quezka.quire.domain

import java.time.LocalDate

enum class ItemKind { CLASS, EVENT, SHIFT }

/** One thing on a day's timeline. A shift past midnight gives one item on each day. */
data class AgendaItem(
    val kind: ItemKind,
    val refUid: String?,
    val day: LocalDate,
    val start: Int,
    val end: Int,
    val title: String,
    val color: String,
    val room: String = "",
    val teacher: String = "",
    val details: String = "",
    val continues: Boolean = false, // the rest of a shift that started the day before
)

data class DayAgenda(
    val day: LocalDate,
    val items: List<AgendaItem>,
    val tasks: List<Task>,
    val journal: String,
)

object Agenda {
    /** Shifts starting on days first..last: one-off ones plus weekly-schedule occurrences,
     *  minus skipped occurrences. */
    fun shifts(jobs: List<Job>, oneOff: List<Shift>, first: LocalDate, last: LocalDate): List<Shift> {
        val result = oneOff.filter { it.day in first..last }.toMutableList()
        var day = first
        while (day <= last) {
            for (job in jobs) {
                for (p in job.patterns) {
                    if (p.occursOn(day) && (day to p.start) !in job.skips) {
                        result += Shift(null, job.uid, day, p.start, p.duration, p.breakMinutes)
                    }
                }
            }
            day = day.plusDays(1)
        }
        return result.sortedWith(compareBy({ it.day }, { it.start }))
    }

    fun itemsOn(
        day: LocalDate,
        courses: List<Course>,
        events: List<Event>,
        jobs: List<Job>,
        shifts: List<Shift>,
    ): List<AgendaItem> {
        val items = mutableListOf<AgendaItem>()
        for (course in courses) {
            for (slot in course.slots.filter { it.weekday == day.weekdayIndex() }) {
                items += AgendaItem(ItemKind.CLASS, course.uid, day, slot.start, slot.end,
                    course.name, course.color, course.roomFor(slot), course.teacher)
            }
        }
        for (e in events.filter { it.day == day }) {
            items += AgendaItem(ItemKind.EVENT, e.uid, day, e.start, e.end, e.title, e.color,
                details = e.details)
        }
        val byUid = jobs.associateBy { it.uid }
        for (s in shifts(jobs, shifts, day.minusDays(1), day)) {
            val job = byUid[s.jobUid]
            val name = job?.name ?: "Shift"
            val color = job?.color ?: "#0090ff"
            if (s.day == day) {
                items += AgendaItem(ItemKind.SHIFT, s.uid ?: s.jobUid, day, s.start,
                    minOf(s.end, MINUTES_PER_DAY), name, color, details = s.notes)
            } else if (s.end > MINUTES_PER_DAY) { // yesterday's shift running past midnight
                items += AgendaItem(ItemKind.SHIFT, s.uid ?: s.jobUid, day, 0,
                    s.end - MINUTES_PER_DAY, name, color, details = s.notes, continues = true)
            }
        }
        return items.sortedWith(compareBy({ it.start }, { it.end }, { it.title }))
    }

    /** Tasks to show on a day: on today, everything overdue plus what's due in the next
     *  two weeks; on other days, what's due that day. */
    fun tasksFor(day: LocalDate, today: LocalDate, tasks: List<Task>): List<Task> {
        val shown = if (day == today) {
            tasks.filter { t ->
                val due = t.due
                due != null && ((!t.done && due < today) || due == today ||
                    (!t.done && due > today && due <= today.plusDays(TODAY_TASK_DAYS.toLong())))
            }
        } else {
            tasks.filter { it.due == day }
        }
        return shown.sortedWith(compareBy({ it.due }, { it.done }, { it.kind != TaskKind.EXAM },
            { it.title.lowercase() }))
    }

    fun groups(tasks: List<Task>, today: LocalDate, includeDone: Boolean): Map<DueBucket, List<Task>> =
        tasks.filter { includeDone || !it.done }
            .sortedWith(compareBy<Task>({ it.due ?: LocalDate.MAX }, { it.title.lowercase() }))
            .groupBy { it.bucket(today) }
            .toSortedMap()
}
