package io.github.quezka.quire.domain

/** Plan my day (0.52): the day's tasks into free time between what's on (= desktop `domain/day_plan.py`). */
object DayPlan {
    const val BLOCK = 45
    const val BREAK = 10
    const val MAX_BLOCKS = 4
    const val DAY_START = 8 * 60
    const val DAY_END = 22 * 60

    data class Slot(val start: Int, val end: Int, val title: String, val ref: String? = null)

    fun freeGaps(busy: List<Pair<Int, Int>>, start: Int = DAY_START, end: Int = DAY_END, pad: Int = BREAK): List<Pair<Int, Int>> {
        val gaps = mutableListOf<Pair<Int, Int>>()
        var at = start
        for ((s0, e0) in busy.sortedWith(compareBy({ it.first }, { it.second }))) {
            val s = s0 - pad; val e = e0 + pad
            if (e <= at) continue
            if (s > at) gaps += at to minOf(s, end)
            at = maxOf(at, e)
            if (at >= end) break
        }
        if (at < end) gaps += at to end
        return gaps.filter { it.second > it.first }
    }

    fun plan(tasks: List<Pair<String?, String>>, busy: List<Pair<Int, Int>>, start: Int = DAY_START, end: Int = DAY_END,
             block: Int = BLOCK, most: Int = MAX_BLOCKS): List<Slot> {
        val slots = mutableListOf<Slot>()
        val gaps = freeGaps(busy, start, end).toMutableList()
        for ((ref, title) in tasks) {
            if (slots.size >= most) break
            val i = gaps.indexOfFirst { it.second - it.first >= block }
            if (i < 0) continue
            val (a, b) = gaps[i]
            slots += Slot(a, a + block, title, ref)
            gaps[i] = (a + block + BREAK) to b
        }
        return slots
    }

    fun roundUp(minute: Int, step: Int = 15) = (minute + step - 1) / step * step

    /** Suggestions for [agenda]; [nowMinute] when it's today (no blocks in the past). */
    fun suggest(agenda: DayAgenda, nowMinute: Int?): List<Slot> {
        val busy = agenda.items.filter { !(it.kind == ItemKind.ROUTINE && it.end - it.start <= MILESTONE_MINUTES) && it.end - it.start < 24 * 60 }
            .map { it.start to it.end }
        val start = maxOf(DAY_START, nowMinute?.let(::roundUp) ?: 0)
        val open = agenda.tasks.filter { !it.done }
        val due = open.filter { it.due != null && !it.due.isAfter(agenda.day) }
        return plan((due.ifEmpty { open }).map { it.uid to it.title }, busy, start, DAY_END)
    }
}
