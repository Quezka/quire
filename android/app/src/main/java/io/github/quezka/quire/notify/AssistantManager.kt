package io.github.quezka.quire.notify

import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Assistant
import io.github.quezka.quire.sync.Settings
import java.time.LocalDateTime

/**
 * Quire as a personal assistant on the phone: a quiet "now and next" glance on the lock screen, a morning and an
 * evening digest, a gentle nudge towards the one next step, and batches of the notifications the hub held back.
 * Each part can be switched off in Settings › Assistant.
 */
class AssistantManager(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val hub: Hub,
    private val water: WaterManager,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    private fun on(key: String) = settings.get("assistant.$key") != "0"
    fun set(key: String, on: Boolean) { settings.set("assistant.$key", if (on) "1" else "0"); plan(); updateNow() }
    fun isOn(key: String) = on(key)

    private fun minuteOf(key: String, default: Int) = settings.get("assistant.$key")?.toIntOrNull() ?: default
    val morningAt get() = minuteOf("morning_at", 7 * 60 + 30)
    val eveningAt get() = minuteOf("evening_at", 21 * 60 + 30)
    val nudgeAt get() = minuteOf("nudge_at", 15 * 60)
    fun setTime(key: String, minute: Int) { settings.set("assistant.$key", minute.coerceIn(0, 24 * 60 - 1).toString()); plan() }

    /** The next moment (today or tomorrow) at [minute]. */
    private fun next(minute: Int): LocalDateTime {
        val t = now()
        val today = t.toLocalDate().atStartOfDay().plusMinutes(minute.toLong())
        return if (today.isAfter(t)) today else today.plusDays(1)
    }

    fun plan() {
        val t = now()
        notifier.wakeAt(Notifier.ACTION_DIGEST, if (on("digest")) minOf(next(morningAt), next(eveningAt)) else null)
        notifier.wakeAt(Notifier.ACTION_NUDGE, if (on("nudges")) next(nudgeAt) else null)
        val minute = t.hour * 60 + t.minute
        val change = Assistant.nextChange(repo.day(t.toLocalDate()).items, minute)
        // the glance changes at the next start or end, and at least every half hour (water, the clock)
        val refresh = t.withSecond(0).withNano(0).plusMinutes(minOf(30, (change ?: (minute + 30)) - minute).toLong().coerceAtLeast(1))
        notifier.wakeAt(Notifier.ACTION_NOW, if (on("glance")) refresh else null)
        notifier.wakeAt(Notifier.ACTION_BATCH, if (hub.enabled && hub.batchHours > 0)
            t.withSecond(0).withNano(0).plusHours(hub.batchHours.toLong()) else null)
    }

    /** The lock-screen glance: what's on now, what's next, today's water. */
    fun updateNow() {
        if (!on("glance")) { notifier.cancelNow(); return }
        val t = now()
        val day = repo.day(t.toLocalDate())
        val (current, coming) = Assistant.nowNext(day.items, t.hour * 60 + t.minute)
        val step = Assistant.nextStep(repo.tasks(), t.toLocalDate())
        notifier.nowNext(current, coming, step, water.drunkToday(), water.profile().reminderGoal)
    }

    /** Morning before 15:00, evening after. The evening one hands over the held notifications and clears them. */
    fun digest() {
        val t = now()
        val today = t.toLocalDate()
        val morning = t.hour < 15
        val day = repo.day(if (morning) today else today.plusDays(1))
        val tasks = repo.tasks()
        val ideas = io.github.quezka.quire.domain.Ideas.caughtBetween(repo.ideas(), today.minusDays(if (morning) 1 else 0), today)
        notifier.digest(morning, day.items, Assistant.dueOn(tasks, day.day), Assistant.overdue(tasks, today),
            ideas.filter { !it.done }.map { it.text }, Assistant.heldLines(hub.held()))
        if (!morning) hub.clearHeld()
    }

    /** Mid-afternoon: one small step, with a button that starts focusing on it. Nothing when there's nothing due. */
    fun nudge() {
        val step = Assistant.nextStep(repo.tasks(), now().toLocalDate()) ?: return
        notifier.nudge(step)
    }

    fun batch() {
        val held = hub.held()
        if (held.isEmpty()) return
        notifier.batch(Assistant.heldLines(held), held.takeLast(5))
        hub.clearHeld()
    }
}
