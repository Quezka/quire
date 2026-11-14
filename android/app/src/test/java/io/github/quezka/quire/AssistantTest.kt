package io.github.quezka.quire

import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.Assistant
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Task
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class AssistantTest {
    private val day = LocalDate.of(2026, 11, 14)
    private fun item(title: String, start: Int, end: Int) = AgendaItem(ItemKind.EVENT, null, day, start, end, title, "#000")

    @Test fun nowAndNextFollowTheClock() {
        val items = listOf(item("Physics", 11 * 60 + 30, 12 * 60 + 30), item("Shift", 15 * 60, 19 * 60))
        assertEquals(null to items[0], Assistant.nowNext(items, 10 * 60).let { it.first to it.second })
        assertEquals(items[0] to items[1], Assistant.nowNext(items, 12 * 60))
        assertEquals(items[1] to null, Assistant.nowNext(items, 16 * 60))
        assertEquals(11 * 60 + 30, Assistant.nextChange(items, 10 * 60))
        assertNull(Assistant.nextChange(items, 20 * 60))
    }

    @Test fun theNextStepIsTheOldestOverdueThenToday() {
        val tasks = listOf(Task("a", "later", due = day.plusDays(3)), Task("b", "today", due = day),
            Task("c", "late", due = day.minusDays(2)), Task("d", "done late", due = day.minusDays(5), done = true))
        assertEquals("late", Assistant.nextStep(tasks, day)?.title)
        assertEquals("today", Assistant.nextStep(tasks.filter { it.uid != "c" }, day)?.title)
        assertEquals(1, Assistant.overdue(tasks, day))
    }

    @Test fun heldNotificationsGroupByApp() {
        val held = listOf(Assistant.Held("WhatsApp", "Sam", "hi", 1), Assistant.Held("Mail", "x", "", 2),
            Assistant.Held("WhatsApp", "Ana", "yo", 3))
        assertEquals(listOf("WhatsApp" to 2, "Mail" to 1), Assistant.heldLines(held))
    }
}
