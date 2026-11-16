package io.github.quezka.quire

import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.notify.Prep
import io.github.quezka.quire.notify.ReminderPlan
import io.github.quezka.quire.notify.ReminderSettings
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime

class PrepTest {
    private val notes = "Dentist\ntravel: 20\n- health card\n- 10 euro\nnot this"

    @Test fun notesSayHowLongToGetThereAndWhatToBring() {
        assertEquals(20, Prep.travelMinutes(notes))
        assertEquals(15, Prep.travelMinutes("Viaggio 15"))
        assertEquals(0, Prep.travelMinutes("no travel here"))
        assertEquals(listOf("health card", "10 euro"), Prep.bring(notes))
    }

    @Test fun travelTimeMakesTheReminderComeEarlier() {
        val day = LocalDate.of(2026, 11, 16)
        val item = AgendaItem(ItemKind.EVENT, "e1", day, 15 * 60, 16 * 60, "Dentist", "#000000", details = notes)
        val plan = ReminderPlan.upcoming(ReminderSettings(minutesBefore = 10), LocalDateTime.of(day, java.time.LocalTime.of(9, 0)),
            { if (it == day) listOf(item) else emptyList() })
        assertEquals(LocalDateTime.of(day, java.time.LocalTime.of(14, 30)), plan.single().at)
    }
}
