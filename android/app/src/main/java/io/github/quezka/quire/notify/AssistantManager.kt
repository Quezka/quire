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

    /** The one main thing for [day] (a task uid), picked the evening before. */
    fun mainFor(day: java.time.LocalDate): String? = settings.get("assistant.main.$day")
    fun setMain(day: java.time.LocalDate, uid: String?) { settings.set("assistant.main.$day", uid); updateNow() }
    fun step(): io.github.quezka.quire.domain.Task? {
        val today = now().toLocalDate()
        return Assistant.nextStep(repo.tasks(), today, mainFor(today))
    }

    /** The next moment (today or tomorrow) at [minute]. */
    private fun next(minute: Int): LocalDateTime {
        val t = now()
        val today = t.toLocalDate().atStartOfDay().plusMinutes(minute.toLong())
        return if (today.isAfter(t)) today else today.plusDays(1)
    }

    fun plan() {
        val t = now()
        notifier.wakeAt(Notifier.ACTION_DIGEST, if (on("digest")) minOf(next(morningAt), next(eveningAt)) else null)
        // two chances a day: the nudge time, and 3 h later if something is stuck (overdue); never after the evening digest
        val second = nudgeAt + 180
        val nudges = listOf(nudgeAt) + (if (second < eveningAt) listOf(second) else emptyList())
        notifier.wakeAt(Notifier.ACTION_NUDGE, if (on("nudges")) nudges.map(::next).minOrNull() else null)
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
        val step = step()
        notifier.nowNext(current, coming, step, water.drunkToday(), water.profile().reminderGoal)
    }

    /** Morning before 15:00, evening after. The evening one hands over the held notifications and clears them. */
    /** Everything the digest says, the same for the notification and Today's Digest button. Morning before 15:00
     *  (today), evening after (tomorrow, and today's ideas). */
    data class DigestParts(val morning: Boolean, val day: java.time.LocalDate, val items: List<io.github.quezka.quire.domain.AgendaItem>,
                           val due: List<io.github.quezka.quire.domain.Task>, val overdue: Int, val ideas: List<String>,
                           val held: List<Pair<String, Int>>, val main: String?, val resurfaced: io.github.quezka.quire.domain.Idea?)

    fun digestParts(): DigestParts {
        val t = now()
        val today = t.toLocalDate()
        val morning = t.hour < 15
        val day = repo.day(if (morning) today else today.plusDays(1))
        val tasks = repo.tasks()
        val all = repo.ideas()
        val ideas = io.github.quezka.quire.domain.Ideas.caughtBetween(all, today.minusDays(if (morning) 1 else 0), today)
        val mainUid = mainFor(day.day)
        val main = tasks.firstOrNull { it.uid == mainUid && !it.done }?.title
        val back = io.github.quezka.quire.domain.Ideas.resurface(all, today, seenIdeas())
        return DigestParts(morning, day.day, day.items, Assistant.dueOn(tasks, day.day), Assistant.overdue(tasks, today),
            ideas.filter { !it.done }.map { it.text }, Assistant.heldLines(hub.held()), main, back)
    }

    private fun seenIdeas(): Map<String, String> = settings.get("ideas.seen").orEmpty().lines()
        .mapNotNull { it.split("=", limit = 2).takeIf { p -> p.size == 2 }?.let { (k, v) -> k to v } }.toMap()

    fun digest() {
        val p = digestParts()
        notifier.digest(p)
        p.resurfaced?.let { idea ->  // shown: not again for two weeks
            settings.set("ideas.seen", (seenIdeas() + (idea.uid to now().toLocalDate().toString()))
                .entries.joinToString("\n") { "${it.key}=${it.value}" })
        }
        if (!p.morning) hub.clearHeld()
    }

    /** The digest right now, asked for by hand (Today's Digest button): title and lines; posts and clears nothing. */
    fun digestNow(): Pair<String, List<String>> {
        val p = digestParts()
        return notifier.digestTitle(p.morning) to notifier.digestLines(p)
    }

    /** Mid-afternoon: one small step, with a button that starts focusing on it. Nothing when there's nothing due. */
    fun nudge() {
        val t = now()
        val today = t.toLocalDate()
        val key = "assistant.nudged.$today"
        val count = settings.get(key)?.toIntOrNull() ?: 0
        val step = step() ?: return
        // the second one only when something is stuck; never more than two a day
        if (count >= 2 || (count == 1 && Assistant.overdue(repo.tasks(), today) == 0)) return
        settings.set(key, (count + 1).toString())
        notifier.nudge(step)
    }

    fun batch() {
        val held = hub.held()
        if (held.isEmpty()) return
        notifier.batch(Assistant.heldLines(held), held.takeLast(5))
        hub.clearHeld()
    }
}
