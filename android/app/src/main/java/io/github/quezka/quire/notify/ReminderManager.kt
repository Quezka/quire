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

    /** key -> when to show it again (the notification's Snooze). */
    private fun snoozed(): Map<String, LocalDateTime> = settings.get("reminders.snoozed").orEmpty().lines()
        .mapNotNull { line -> line.split("=", limit = 2).takeIf { it.size == 2 }
            ?.let { (k, v) -> runCatching { k to LocalDateTime.parse(v) }.getOrNull() } }.toMap()

    private fun saveSnoozed(map: Map<String, LocalDateTime>) =
        settings.set("reminders.snoozed", map.entries.joinToString("\n") { "${it.key}=${it.value}" })

    /** Snooze a reminder [minutes] (it comes back, unless the thing has started by then). */
    fun snooze(key: String, minutes: Long = 5) {
        saveSnoozed(snoozed() + (key to now().plusMinutes(minutes)))
        plan()
    }

    /** Show what's due now (a minute early is fine: alarms can come a little early). */
    fun fire() {
        val time = now()
        val sent = sent()
        val coming = upcoming(time.minusMinutes(2))
        val due = coming.filter { it.at <= time.plusMinutes(1) && it.key !in sent }
        for (r in due) notifier.reminder(r, time)
        // snoozed ones whose time came: once more
        val snoozed = snoozed()
        val again = snoozed.filterValues { it <= time.plusMinutes(1) }.keys
        for (r in coming.filter { it.key in again }) notifier.reminder(r, time)
        saveSnoozed(snoozed.filterKeys { it !in again && coming.any { r -> r.key == it } })
        // Keep only keys of things that haven't started yet.
        val keep = (sent + due.map { it.key }).filter { key ->
            runCatching { LocalDateTime.parse(key.substringAfterLast('|')) > time.minusHours(1) }.getOrDefault(false)
        }
        settings.set("reminders.sent", keep.joinToString("\n"))
    }

    /** Set the alarm for the next reminder not shown yet. */
    fun plan() {
        val sent = sent()
        val next = upcoming(now()).firstOrNull { it.key !in sent }?.at
        val snooze = snoozed().values.minOrNull()
        notifier.wakeAt(Notifier.ACTION_REMIND, listOfNotNull(next, snooze).minOrNull())
    }
}
