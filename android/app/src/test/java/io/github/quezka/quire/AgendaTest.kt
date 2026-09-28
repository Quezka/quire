package io.github.quezka.quire

import io.github.quezka.quire.domain.Agenda
import io.github.quezka.quire.domain.DueBucket
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.deriveNoteTitle
import io.github.quezka.quire.domain.normalizeTopic
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class AgendaTest {
    private val saturday = LocalDate.of(2026, 9, 26)

    @Test fun overnightWeeklyShiftSpansTwoDays() {
        val bar = Job("j", "Bar", patterns = listOf(ShiftPattern(5, 19 * 60, 6 * 60)))
        val sat = Agenda.itemsOn(saturday, emptyList(), emptyList(), listOf(bar), emptyList())
        val sun = Agenda.itemsOn(saturday.plusDays(1), emptyList(), emptyList(), listOf(bar), emptyList())
        assertEquals(listOf(19 * 60 to 24 * 60), sat.map { it.start to it.end })
        assertEquals(listOf(0 to 60), sun.map { it.start to it.end })
        assertTrue(sun.single().continues)
    }

    @Test fun skipsSinceUntilAndOneOffShifts() {
        val job = Job("j", "Café",
            patterns = listOf(ShiftPattern(5, 600, 60, since = saturday, until = saturday.plusWeeks(2))),
            skips = setOf(saturday.plusWeeks(1) to 600))
        val one = Shift("s", "j", saturday.plusDays(1), 900, 120)
        val days = Agenda.shifts(listOf(job), listOf(one), saturday.minusWeeks(1), saturday.plusWeeks(4))
            .map { it.day }
        assertEquals(listOf(saturday, saturday.plusDays(1), saturday.plusWeeks(2)), days)
    }

    @Test fun todayShowsOverdueAndTheNextTwoWeeks() {
        val today = LocalDate.of(2026, 9, 23)
        val tasks = listOf(
            Task("1", "late", due = today.minusDays(2)),
            Task("2", "late but done", due = today.minusDays(2), done = true),
            Task("3", "soon", due = today.plusDays(6)),
            Task("4", "far", due = today.plusDays(30)),
            Task("5", "undated"),
        )
        assertEquals(listOf("late", "soon"), Agenda.tasksFor(today, today, tasks).map { it.title })
        assertEquals(listOf("far"), Agenda.tasksFor(today.plusDays(30), today, tasks).map { it.title })
        val groups = Agenda.groups(tasks, today, includeDone = false)
        assertEquals(listOf(DueBucket.OVERDUE, DueBucket.UPCOMING, DueBucket.LATER, DueBucket.UNDATED),
            groups.keys.toList())
    }

    @Test fun noteTitlesAndTopicsMatchTheDesktop() {
        assertEquals("Mitochondria", deriveNoteTitle("\n# Mitochondria\n\nPowerhouse"))
        assertEquals("Untitled", deriveNoteTitle("   \n"))
        assertEquals("Cell biology", normalizeTopic("  Cell   biology "))
    }
}
