package io.github.quezka.quire.notify

import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.sync.Settings
import java.time.LocalDate
import java.time.LocalDateTime

/** "Remind me before my next thing starts", with the desktop's settings and defaults
 *  (application/services/reminders.py). */
data class ReminderSettings(
    val minutesBefore: Int? = 10, // null: no reminders
    val events: Boolean = true,
    val classes: Boolean = false,
    val shifts: Boolean = true,
) {
    fun wants(kind: ItemKind) = when (kind) {
        ItemKind.CLASS -> classes
        ItemKind.EVENT, ItemKind.ROUTINE -> events
        ItemKind.SHIFT -> shifts
    }

    companion object {
        val CHOICES = listOf(null, 0, 5, 10, 15, 30, 60)

        fun load(settings: Settings): ReminderSettings {
            val d = ReminderSettings()
            val minutes = settings.get("reminders.minutes")
            fun flag(name: String, default: Boolean) = settings.get("reminders.$name")?.let { it == "1" } ?: default
            return ReminderSettings(
                if (minutes == null) d.minutesBefore else minutes.toIntOrNull(),
                flag("events", d.events), flag("classes", d.classes), flag("shifts", d.shifts))
        }
    }

    fun save(settings: Settings) {
        settings.set("reminders.minutes", minutesBefore?.toString() ?: "off")
        settings.set("reminders.events", if (events) "1" else "0")
        settings.set("reminders.classes", if (classes) "1" else "0")
        settings.set("reminders.shifts", if (shifts) "1" else "0")
    }
}

/** One reminder: when to show it, and for what. */
data class Reminder(val at: LocalDateTime, val starts: LocalDateTime, val item: AgendaItem) {
    val key get() = "${item.kind}|${item.refUid}|$starts"
}

object ReminderPlan {
    /** Reminders for things starting from [now] to [now] + [hours], soonest first. The
     *  after-midnight part of a shift that began the day before isn't announced again. */
    fun upcoming(settings: ReminderSettings, now: LocalDateTime, itemsOn: (LocalDate) -> List<AgendaItem>,
                 hours: Long = 36): List<Reminder> {
        val before = settings.minutesBefore ?: return emptyList()
        val horizon = now.plusHours(hours)
        val result = mutableListOf<Reminder>()
        var day = now.toLocalDate()
        while (day <= horizon.toLocalDate()) {
            for (item in itemsOn(day)) {
                if (item.continues || item.isAllDay || !settings.wants(item.kind)) continue
                val starts = day.atStartOfDay().plusMinutes(item.start.toLong())
                if (starts <= now || starts > horizon) continue
                val lead = before + Prep.travelMinutes(item.details)
                result += Reminder(maxOf(starts.minusMinutes(lead.toLong()), now), starts, item)
            }
            day = day.plusDays(1)
        }
        return result.sortedBy { it.at }
    }
}


/** What to get ready before something starts, read from its notes (no new fields, so it syncs as it is):
 *  `travel: 20` (also viaggio / дорога) = minutes to get there, the reminder comes that much earlier;
 *  lines starting with `-` = things to bring. */
object Prep {
    private val TRAVEL = Regex("(?i)\\b(travel|viaggio|дорога)\\s*:?\\s*(\\d{1,3})")

    fun travelMinutes(details: String): Int = TRAVEL.find(details)?.groupValues?.get(2)?.toIntOrNull() ?: 0

    fun bring(details: String, max: Int = 5): List<String> = details.lineSequence().map { it.trim() }
        .filter { it.startsWith("-") || it.startsWith("•") }.map { it.trimStart('-', '•', ' ') }
        .filter { it.isNotEmpty() }.take(max).toList()
}
