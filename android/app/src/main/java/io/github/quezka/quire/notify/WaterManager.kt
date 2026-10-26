package io.github.quezka.quire.notify

import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Water
import io.github.quezka.quire.domain.WaterProfile
import io.github.quezka.quire.sync.Settings
import java.time.LocalDateTime

/** The water profile on this device, and the reminders that nudge you when you fall behind. */
class WaterManager(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    fun profile(): WaterProfile {
        fun num(key: String) = settings.get("water.$key")?.toDoubleOrNull()
        val d = WaterProfile()
        return WaterProfile(num("height"), num("weight"), num("glass")?.toInt() ?: d.glass,
            settings.get("water.remind") != "0", num("start")?.toInt() ?: d.start, num("end")?.toInt() ?: d.end)
    }

    fun save(p: WaterProfile) {
        settings.set("water.height", p.heightCm?.toString()); settings.set("water.weight", p.weightKg?.toString())
        settings.set("water.glass", p.glass.toString()); settings.set("water.remind", if (p.remind) "1" else "0")
        settings.set("water.start", p.start.toString()); settings.set("water.end", p.end.toString())
        plan()
    }

    fun drunkToday() = repo.waterOn(repo.today()).sumOf { it.ml }

    /** Show a nudge now if behind the pace and not just reminded; the next check is planned either way. */
    fun check() {
        val p = profile()
        val goal = p.goal
        val time = now()
        val minute = time.hour * 60 + time.minute
        val last = settings.get("water.last")?.split("@")?.takeIf { it.size == 2 && it[0] == time.toLocalDate().toString() }
            ?.get(1)?.toIntOrNull()
        if (p.remind && goal != null && Water.reminderDue(goal, drunkToday(), minute, last, p.start, p.end)) {
            settings.set("water.last", "${time.toLocalDate()}@$minute")
            notifier.water(drunkToday(), goal)
        }
        plan()
    }

    /** One alarm for the next check: every half hour in the waking window, else the next morning. */
    fun plan() {
        val p = profile()
        if (!p.remind || p.goal == null) { notifier.wakeAt(Notifier.ACTION_WATER, null); return }
        val time = now()
        val minute = time.hour * 60 + time.minute
        val next = when {
            minute < p.start -> time.toLocalDate().atStartOfDay().plusMinutes(p.start.toLong())
            minute >= p.end - 30 -> time.toLocalDate().plusDays(1).atStartOfDay().plusMinutes(p.start.toLong())
            else -> time.withSecond(0).withNano(0).plusMinutes(30)
        }
        notifier.wakeAt(Notifier.ACTION_WATER, next)
    }
}
