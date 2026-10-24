package io.github.quezka.quire.domain

import io.github.quezka.quire.sync.Settings
import java.time.LocalDate
import java.time.LocalDateTime

/** Silence notifications while these things are on (mirrors the desktop's services/quiet.py).
 *  Milestones and routines have no duration, so they never silence anything. */
data class QuietSettings(
    val enabled: Boolean = false,
    val classes: Boolean = true,
    val events: Boolean = true,
    val shifts: Boolean = false,
) {
    fun wants(kind: ItemKind) = when (kind) {
        ItemKind.CLASS -> classes
        ItemKind.EVENT -> events
        ItemKind.SHIFT -> shifts
        ItemKind.ROUTINE -> false
    }

    fun save(settings: Settings) {
        settings.set("quiet.enabled", if (enabled) "1" else "0")
        settings.set("quiet.classes", if (classes) "1" else "0")
        settings.set("quiet.events", if (events) "1" else "0")
        settings.set("quiet.shifts", if (shifts) "1" else "0")
    }

    companion object {
        fun load(settings: Settings): QuietSettings {
            val d = QuietSettings()
            fun flag(name: String, default: Boolean) = settings.get("quiet.$name")?.let { it == "1" } ?: default
            return QuietSettings(flag("enabled", d.enabled), flag("classes", d.classes),
                flag("events", d.events), flag("shifts", d.shifts))
        }
    }
}

data class QuietStatus(val active: Boolean, val until: LocalDateTime?, val nextStart: LocalDateTime?)

object Quiet {
    fun merge(periods: List<Pair<LocalDateTime, LocalDateTime>>): List<Pair<LocalDateTime, LocalDateTime>> {
        val merged = mutableListOf<Pair<LocalDateTime, LocalDateTime>>()
        for ((start, end) in periods.sortedBy { it.first }) {
            val last = merged.lastOrNull()
            if (last != null && start <= last.second) merged[merged.size - 1] = last.first to maxOf(last.second, end)
            else merged += start to end
        }
        return merged
    }

    /** What is on from [now] to the end of tomorrow, as merged periods (a shift over midnight is one). */
    fun periods(now: LocalDateTime, settings: QuietSettings, itemsOn: (LocalDate) -> List<AgendaItem>):
        List<Pair<LocalDateTime, LocalDateTime>> {
        val found = mutableListOf<Pair<LocalDateTime, LocalDateTime>>()
        for (day in listOf(now.toLocalDate(), now.toLocalDate().plusDays(1))) {
            for (item in itemsOn(day)) {
                if (item.isMilestone || !settings.wants(item.kind)) continue
                val midnight = day.atStartOfDay()
                found += midnight.plusMinutes(item.start.toLong()) to midnight.plusMinutes(item.end.toLong())
            }
        }
        return merge(found)
    }

    fun status(periods: List<Pair<LocalDateTime, LocalDateTime>>, now: LocalDateTime): QuietStatus {
        val merged = merge(periods)
        merged.firstOrNull { now >= it.first && now < it.second }?.let { return QuietStatus(true, it.second, null) }
        return QuietStatus(false, null, merged.map { it.first }.filter { it > now }.minOrNull())
    }
}
