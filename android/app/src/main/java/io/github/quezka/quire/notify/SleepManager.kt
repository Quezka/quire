package io.github.quezka.quire.notify

import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.DEFAULT_SLEEP_HOURS
import io.github.quezka.quire.domain.DEFAULT_WAKE
import io.github.quezka.quire.domain.Sleep
import io.github.quezka.quire.domain.SleepLog
import io.github.quezka.quire.sync.Settings
import java.time.Duration
import java.time.LocalDateTime

/** One-tap logging ("I'm going to sleep" / "I'm awake") and the bedtime nudge. */
class SleepManager(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    fun goalHours() = settings.get("sleep.hours")?.toDoubleOrNull() ?: DEFAULT_SLEEP_HOURS
    fun wake() = settings.get("sleep.wake")?.toIntOrNull() ?: DEFAULT_WAKE
    fun bedtime() = Sleep.bedtimeFor(wake(), goalHours())
    fun remindEnabled() = settings.get("sleep.remind") != "0"
    fun setRemind(on: Boolean) { settings.set("sleep.remind", if (on) "1" else "0"); plan() }

    fun asleepSince(): LocalDateTime? = settings.get("sleep.pending")?.let { runCatching { LocalDateTime.parse(it) }.getOrNull() }

    fun goToSleep() { settings.set("sleep.pending", now().withSecond(0).withNano(0).toString()); plan() }
    fun cancel() { settings.set("sleep.pending", null) }

    /** Close the night started with [goToSleep], waking now; null if nothing was started or it was
     *  more than 18 hours ago or less than 30 minutes ago. */
    fun wakeUp(): SleepLog? {
        val since = asleepSince() ?: return null
        val time = now()
        val minutes = Duration.between(since, time).toMinutes()
        if (minutes < 30 || minutes > 18 * 60) return null
        val log = SleepLog(time.toLocalDate(), since.hour * 60 + since.minute, time.hour * 60 + time.minute)
        repo.saveSleep(log)
        settings.set("sleep.pending", null)
        return log
    }

    /** Nudge once, 30 minutes before the bedtime goal. */
    fun check() {
        val time = now()
        val minute = time.hour * 60 + time.minute
        val today = time.toLocalDate().toString()
        if (remindEnabled() && asleepSince() == null && settings.get("sleep.reminded") != today &&
            Sleep.shouldWindDown(minute, bedtime())) {
            settings.set("sleep.reminded", today)
            notifier.windDown(bedtime())
        }
        plan()
    }

    /** The alarm for the next wind-down time (bedtime minus 30 minutes). */
    fun plan() {
        if (!remindEnabled() || asleepSince() != null) { notifier.wakeAt(Notifier.ACTION_SLEEP, null); return }
        val time = now()
        val start = Math.floorMod(bedtime() - 30, 24 * 60)
        var at = time.toLocalDate().atStartOfDay().plusMinutes(start.toLong())
        if (at <= time) at = at.plusDays(1)
        notifier.wakeAt(Notifier.ACTION_SLEEP, at)
    }
}
