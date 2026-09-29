package io.github.quezka.quire.domain

import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime

/** The Pomodoro timer, with the desktop's rules (domain/focus.py). Time is always passed in,
 *  so the timer measures against the clock and survives the app being closed. */

enum class Phase(val code: String) {
    WORK("work"), SHORT_BREAK("short_break"), LONG_BREAK("long_break");

    companion object {
        fun of(code: String?) = entries.firstOrNull { it.code == code } ?: WORK
    }
}

data class FocusSettings(
    val workMinutes: Int = 25,
    val shortBreakMinutes: Int = 5,
    val longBreakMinutes: Int = 15,
    val rounds: Int = 4, // focus sessions before a long break
    val autoContinue: Boolean = true,
) {
    fun minutes(phase: Phase) = when (phase) {
        Phase.WORK -> workMinutes
        Phase.SHORT_BREAK -> shortBreakMinutes
        Phase.LONG_BREAK -> longBreakMinutes
    }

    fun valid() = workMinutes in 1..180 && shortBreakMinutes in 1..60 &&
        longBreakMinutes in 1..120 && rounds in 1..12
}

/** A finished phase, reported by [PomodoroTimer.tick]. */
data class PhaseEnded(val phase: Phase, val started: Instant, val minutes: Int, val next: Phase)

/** Everything the timer knows; saved so it keeps running while the app is closed. */
data class TimerState(
    val phase: Phase = Phase.WORK,
    val completed: Int = 0,
    val remainingMs: Long? = null, // null: the phase's full length
    val endsAt: Instant? = null, // set while running
    val startedAt: Instant? = null, // when the current phase first started
)

class PomodoroTimer(var settings: FocusSettings = FocusSettings(), var state: TimerState = TimerState()) {
    val running get() = state.endsAt != null
    val started get() = state.startedAt != null
    val phase get() = state.phase
    val completed get() = state.completed
    private val duration get() = Duration.ofMinutes(settings.minutes(state.phase).toLong())

    fun remaining(now: Instant): Duration {
        val ends = state.endsAt ?: return state.remainingMs?.let(Duration::ofMillis) ?: duration
        return Duration.between(now, ends).coerceAtLeast(Duration.ZERO)
    }

    fun progress(now: Instant): Float {
        val total = duration.toMillis().toFloat()
        return if (total > 0) 1 - remaining(now).toMillis() / total else 1f
    }

    /** Which focus session of the cycle this is (1-based). */
    val round get() = minOf(state.completed + if (state.phase == Phase.WORK) 1 else 0, settings.rounds)

    fun start(now: Instant) {
        if (running) return
        state = state.copy(startedAt = state.startedAt ?: now, endsAt = now + remaining(now), remainingMs = null)
    }

    fun pause(now: Instant) {
        if (running) state = state.copy(remainingMs = remaining(now).toMillis(), endsAt = null)
    }

    fun toggle(now: Instant) = if (running) pause(now) else start(now)

    fun reset() {
        state = TimerState()
    }

    /** Jump to the next phase without counting this one as done. */
    fun skip(now: Instant) = enter(nextPhase(counting = false), if (running) now else null)

    fun applySettings(new: FocusSettings) {
        settings = new
        if (!started) state = state.copy(remainingMs = null)
    }

    /** Advance if the running phase has run out; report what ended. */
    fun tick(now: Instant): PhaseEnded? {
        val ends = state.endsAt ?: return null
        if (now < ends) return null
        val event = PhaseEnded(state.phase, state.startedAt ?: (ends - duration),
            settings.minutes(state.phase), nextPhase(counting = true, dryRun = true))
        enter(nextPhase(counting = true), if (settings.autoContinue) ends else null)
        return event
    }

    private fun nextPhase(counting: Boolean, dryRun: Boolean = false): Phase {
        if (state.phase != Phase.WORK) {
            if (!dryRun && state.phase == Phase.LONG_BREAK) state = state.copy(completed = 0)
            return Phase.WORK
        }
        val done = state.completed + if (counting) 1 else 0
        if (!dryRun) state = state.copy(completed = done)
        return if (done >= settings.rounds) Phase.LONG_BREAK else Phase.SHORT_BREAK
    }

    private fun enter(phase: Phase, runningFrom: Instant?) {
        val length = Duration.ofMinutes(settings.minutes(phase).toLong())
        state = state.copy(phase = phase, remainingMs = null, startedAt = runningFrom,
            endsAt = runningFrom?.plus(length))
    }
}

/** A finished focus session, synced like on the desktop (kind "focus"). */
data class FocusSession(
    val uid: String,
    val started: LocalDateTime,
    val minutes: Int,
    val taskUid: String? = null,
    val label: String = "",
)

data class FocusStats(
    val todaySessions: Int,
    val todayMinutes: Int,
    val weekSessions: Int,
    val weekMinutes: Int,
    val todayByProject: List<Pair<String, Int>>,
)

fun focusStats(sessions: List<FocusSession>, today: java.time.LocalDate): FocusStats {
    val monday = today.monday()
    val week = sessions.filter { it.started.toLocalDate() in monday..monday.plusDays(6) }
    val todays = week.filter { it.started.toLocalDate() == today }
    val projects = todays.filter { it.label.isNotBlank() }.groupBy { it.label }
        .map { (label, list) -> label to list.sumOf { it.minutes } }
        .sortedWith(compareBy({ -it.second }, { it.first }))
    return FocusStats(todays.size, todays.sumOf { it.minutes }, week.size, week.sumOf { it.minutes }, projects)
}
