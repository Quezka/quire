package io.github.quezka.quire.notify

import android.app.NotificationManager
import android.content.Context
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Quiet
import io.github.quezka.quire.domain.QuietSettings
import io.github.quezka.quire.domain.QuietStatus
import io.github.quezka.quire.sync.Settings
import java.time.LocalDateTime

/**
 * Turns Do Not Disturb (alarms only) on while a class, event or shift is on, and back to what
 * it was afterwards. It only undoes its own change: if you switched the mode yourself in the
 * meantime, that wins. Needs "Do Not Disturb access", which the user grants in system settings.
 */
class QuietManager(
    private val context: Context,
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    private val manager get() = context.getSystemService(NotificationManager::class.java)

    fun settings() = QuietSettings.load(settings)

    fun save(new: QuietSettings) {
        new.save(settings)
        update()
    }

    fun hasAccess(): Boolean = manager.isNotificationPolicyAccessGranted

    fun status(): QuietStatus {
        val s = settings()
        if (!s.enabled) return QuietStatus(false, null, null)
        val time = now()
        return Quiet.status(Quiet.periods(time, s) { repo.day(it).items }, time)
    }

    /** Bring Do Not Disturb in line with the schedule and set the alarm for the next change. */
    fun update() {
        val status = status()
        val owned = settings.get("quiet.applied") != null
        val granted = hasAccess()
        if (status.active && granted && !owned) {
            settings.set("quiet.applied", manager.currentInterruptionFilter.toString())
            manager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALARMS)
        } else if ((!status.active || !granted) && owned) {
            val before = settings.get("quiet.applied")?.toIntOrNull() ?: NotificationManager.INTERRUPTION_FILTER_ALL
            // Only undo our own change; if the mode was changed by hand since, leave it.
            if (granted && manager.currentInterruptionFilter == NotificationManager.INTERRUPTION_FILTER_ALARMS) {
                manager.setInterruptionFilter(before)
            }
            settings.set("quiet.applied", null)
        }
        notifier.wakeAt(Notifier.ACTION_QUIET, status.until ?: status.nextStart)
    }
}
