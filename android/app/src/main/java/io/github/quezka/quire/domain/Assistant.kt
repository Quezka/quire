package io.github.quezka.quire.domain

import java.time.LocalDate

/**
 * The assistant's rules (pure): what's happening now and next, the one next step to take, and what goes in the
 * morning and evening digest. ADHD-friendly on purpose: one thing at a time, nothing to decide.
 */
object Assistant {
    /** The item going on at [minute] (if any) and the next one to start after it. */
    fun nowNext(items: List<AgendaItem>, minute: Int): Pair<AgendaItem?, AgendaItem?> {
        val sorted = items.filter { it.end > it.start }.sortedBy { it.start }
        val now = sorted.lastOrNull { it.start <= minute && minute < it.end }
        val next = sorted.firstOrNull { it.start > minute && it !== now }
        return now to next
    }

    /** When the now/next glance must change: the next start or end after [minute] (null: nothing more today). */
    fun nextChange(items: List<AgendaItem>, minute: Int): Int? =
        items.flatMap { listOf(it.start, it.end) }.filter { it > minute }.minOrNull()

    /** The one task to do next: overdue first (oldest due), then due today, then the soonest; never more than one. */
    fun nextStep(tasks: List<Task>, today: LocalDate): Task? {
        val open = tasks.filter { !it.done }
        return open.filter { it.due != null && it.due < today }.minByOrNull { it.due!! }
            ?: open.filter { it.due == today }.minByOrNull { it.title.lowercase() }
            ?: open.filter { it.due != null }.minByOrNull { it.due!! }
    }

    fun overdue(tasks: List<Task>, today: LocalDate) = tasks.count { !it.done && it.due != null && it.due < today }
    fun dueOn(tasks: List<Task>, day: LocalDate) = tasks.filter { !it.done && it.due == day }

    /** One app's notification, held back by the hub for the digest. */
    data class Held(val app: String, val title: String, val text: String, val at: Long)

    /** Held notifications as digest lines: one line per app, the count and the latest title. */
    fun heldLines(held: List<Held>): List<Pair<String, Int>> =
        held.groupBy { it.app }.map { (app, list) -> app to list.size }.sortedByDescending { it.second }
}
