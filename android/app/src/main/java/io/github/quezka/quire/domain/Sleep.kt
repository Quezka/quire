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
)

object Sleep {
    /** When to be asleep to wake at [wake] after [hours] of sleep. */
    fun bedtimeFor(wake: Int, hours: Double) = Math.floorMod(wake - Math.round(hours * 60).toInt(), MINUTES_PER_DAY)

    // Bedtimes either side of midnight average sensibly when measured from noon.
    private fun fromNoon(minute: Int) = Math.floorMod(minute - 12 * 60, MINUTES_PER_DAY)

    fun stats(logs: List<SleepLog>, goalHours: Double): SleepStats {
        if (logs.isEmpty()) return SleepStats(0, 0, null, null, null, 0, 0)
        val goal = Math.round(goalHours * 60).toInt()
        val n = logs.size
        val bed = logs.sumOf { fromNoon(it.asleep) } / n
        val rated = logs.mapNotNull { it.quality }
        return SleepStats(n, logs.sumOf { it.minutes } / n, (bed + 12 * 60) % MINUTES_PER_DAY,
            logs.sumOf { it.woke } / n, rated.takeIf { it.isNotEmpty() }?.average(),
            logs.count { it.minutes >= goal * 0.9 }, logs.sumOf { maxOf(0, goal - it.minutes) })
    }
}
