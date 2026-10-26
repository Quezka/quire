package io.github.quezka.quire.domain

import java.time.LocalDate

const val MIN_SLEEP = 30
const val MAX_SLEEP = 18 * 60
const val DEFAULT_SLEEP_HOURS = 8.0
const val DEFAULT_WAKE = 6 * 60

/** One night, logged on the day you woke up (the desktop's domain/sleep.py). */
data class SleepLog(
    val day: LocalDate,
    val asleep: Int, // minutes after midnight
    val woke: Int,
    val quality: Int? = null, // 1 (awful) to 5 (great)
    val note: String = "",
) {
    val minutes get() = Math.floorMod(woke - asleep, MINUTES_PER_DAY)
    fun valid() = asleep in 0 until MINUTES_PER_DAY && woke in 0 until MINUTES_PER_DAY &&
        minutes in MIN_SLEEP..MAX_SLEEP && (quality == null || quality in 1..5)
}

data class SleepStats(
    val nights: Int, val averageMinutes: Int, val averageBedtime: Int?, val averageWake: Int?,
    val averageQuality: Double?, val enough: Int, val shortfallMinutes: Int,
    val bedtimeSpread: Int = 0, val streak: Int = 0,
) {
    /** "steady", "mixed" or "irregular" from how far bedtimes wander; blank until a few nights. */
    val regularity get() = when {
        nights < 3 -> ""
        bedtimeSpread <= 30 -> "steady"
        bedtimeSpread <= 60 -> "mixed"
        else -> "irregular"
    }
}

object Sleep {
    /** When to be asleep to wake at [wake] after [hours] of sleep. */
    fun bedtimeFor(wake: Int, hours: Double) = Math.floorMod(wake - Math.round(hours * 60).toInt(), MINUTES_PER_DAY)

    // Bedtimes either side of midnight average sensibly when measured from noon.
    private fun fromNoon(minute: Int) = Math.floorMod(minute - 12 * 60, MINUTES_PER_DAY)

    /** Nights in a row, up to the latest, that reached the goal. */
    fun streak(logs: List<SleepLog>, goalHours: Double): Int {
        val goal = Math.round(goalHours * 60).toInt()
        var run = 0
        var previous: LocalDate? = null
        for (log in logs.sortedByDescending { it.day }) {
            if (log.minutes < goal * 0.9 || (previous != null && java.time.temporal.ChronoUnit.DAYS.between(log.day, previous) != 1L)) break
            run++; previous = log.day
        }
        return run
    }

    /** Within [lead] minutes before bedtime (measured around midnight). */
    fun shouldWindDown(minute: Int, bedtime: Int, lead: Int = 30): Boolean {
        val ahead = Math.floorMod(bedtime - minute, MINUTES_PER_DAY)
        return ahead in 1..lead
    }

    fun stats(logs: List<SleepLog>, goalHours: Double): SleepStats {
        if (logs.isEmpty()) return SleepStats(0, 0, null, null, null, 0, 0)
        val goal = Math.round(goalHours * 60).toInt()
        val n = logs.size
        val evenings = logs.map { fromNoon(it.asleep) }
        val bed = evenings.sum() / n
        val mean = evenings.sum().toDouble() / n
        val spread = Math.round(Math.sqrt(evenings.sumOf { (it - mean) * (it - mean) } / n)).toInt()
        val rated = logs.mapNotNull { it.quality }
        return SleepStats(n, logs.sumOf { it.minutes } / n, (bed + 12 * 60) % MINUTES_PER_DAY,
            logs.sumOf { it.woke } / n, rated.takeIf { it.isNotEmpty() }?.average(),
            logs.count { it.minutes >= goal * 0.9 }, logs.sumOf { maxOf(0, goal - it.minutes) },
            spread, streak(logs, goalHours))
    }
}
