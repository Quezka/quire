package io.github.quezka.quire.notify

import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.sync.Settings
import java.time.LocalDateTime

/**
 * Keeps one alarm set for the next reminder. When it goes off, everything due is shown
 * once (remembered across restarts), and the next one is planned.
 */
class ReminderManager(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    fun settings() = ReminderSettings.load(settings)

    fun save(new: ReminderSettings) {
        new.save(settings)
        plan()
    }

    private fun upcoming(from: LocalDateTime) = ReminderPlan.upcoming(settings(), from, { repo.day(it).items })

    private fun sent(): Set<String> = settings.get("reminders.sent")?.split("\n")?.filter { it.isNotEmpty() }?.toSet() ?: emptySet()

    /** Show what's due now (a minute early is fine: alarms can come a little early). */
    fun fire() {
        val time = now()
        val sent = sent()
        val due = upcoming(time.minusMinutes(2)).filter { it.at <= time.plusMinutes(1) && it.key !in sent }
        for (r in due) notifier.reminder(r, time)
        // Keep only keys of things that haven't started yet.
        val keep = (sent + due.map { it.key }).filter { key ->
            runCatching { LocalDateTime.parse(key.substringAfterLast('|')) > time.minusHours(1) }.getOrDefault(false)
        }
        settings.set("reminders.sent", keep.joinToString("\n"))
    }

    /** Set the alarm for the next reminder not shown yet. */
    fun plan() {
        val sent = sent()
        val next = upcoming(now()).firstOrNull { it.key !in sent }
        notifier.wakeAt(Notifier.ACTION_REMIND, next?.at)
    }
}
