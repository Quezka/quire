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
            settings.set("quiet.applied", restoreTo(manager.currentInterruptionFilter).toString())
            manager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALARMS)
        } else if ((!status.active || !granted) && owned) {
            if (granted) {
                val before = settings.get("quiet.applied")?.toIntOrNull() ?: NotificationManager.INTERRUPTION_FILTER_ALL
                // The event is over, so Do Not Disturb goes back whatever the phone reports it as now: it
                // can be other than "alarms" (another rule merged in, a maker's own modes), and staying
                // silenced by mistake is worse than undoing a change made by hand during the event.
                if (manager.currentInterruptionFilter != before) manager.setInterruptionFilter(restoreTo(before))
                settings.set("quiet.applied", null)
            }  // no access any more: remembered, and undone as soon as it comes back
        }
        notifier.wakeAt(Notifier.ACTION_QUIET, status.until ?: status.nextStart)
        // A second look a little later, in case the phone's battery saving swallows the alarm at the end.
        notifier.wakeAt(Notifier.ACTION_QUIET_AGAIN, status.until?.plusMinutes(2))
    }

    /** What to go back to: never "alarms" or an unknown state, which would only be a silence left behind. */
    private fun restoreTo(filter: Int) = when (filter) {
        NotificationManager.INTERRUPTION_FILTER_PRIORITY, NotificationManager.INTERRUPTION_FILTER_NONE -> filter
        else -> NotificationManager.INTERRUPTION_FILTER_ALL
    }
}
