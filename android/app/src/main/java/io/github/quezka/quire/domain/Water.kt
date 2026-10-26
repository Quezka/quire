package io.github.quezka.quire.domain

import java.time.LocalDate
import kotlin.math.sqrt

const val WATER_MIN_GOAL = 1200
const val WATER_MAX_GOAL = 4500
const val WATER_MAX_SIP = 2000
const val WATER_GLASS = 250
const val WATER_START = 8 * 60
const val WATER_END = 22 * 60
const val WATER_BEHIND = 250
const val WATER_REMIND_EVERY = 90

/** One glass, logged at a time of day (the desktop's domain/water.py). */
data class WaterLog(val uid: String, val day: LocalDate, val at: Int, val ml: Int)

object Water {
    /** From body surface area (Mosteller) at 1200 ml per square metre, rounded to 50 ml. */
    fun goal(heightCm: Double, weightKg: Double): Int? {
        if (heightCm !in 80.0..250.0 || weightKg !in 20.0..300.0) return null
        val area = sqrt(heightCm * weightKg / 3600)
        return (Math.round(area * 1200 / 50) * 50).toInt().coerceIn(WATER_MIN_GOAL, WATER_MAX_GOAL)
    }

    /** How much should have been drunk by [minute], spread evenly across the waking day. */
    fun expected(goal: Int, minute: Int, start: Int = WATER_START, end: Int = WATER_END): Int = when {
        minute <= start -> 0
        minute >= end -> goal
        else -> Math.round(goal.toDouble() * (minute - start) / (end - start)).toInt()
    }

    fun reminderDue(goal: Int, drunk: Int, minute: Int, lastReminder: Int?,
                    start: Int = WATER_START, end: Int = WATER_END): Boolean {
        if (minute !in start until end || drunk >= goal) return false
        if (lastReminder != null && minute - lastReminder in 0 until WATER_REMIND_EVERY) return false
        return expected(goal, minute, start, end) - drunk >= WATER_BEHIND
    }
}

data class WaterProfile(
    val heightCm: Double? = null, val weightKg: Double? = null, val glass: Int = WATER_GLASS,
    val remind: Boolean = true, val start: Int = WATER_START, val end: Int = WATER_END,
) {
    val goal: Int? get() = if (heightCm != null && weightKg != null) Water.goal(heightCm, weightKg) else null
}
