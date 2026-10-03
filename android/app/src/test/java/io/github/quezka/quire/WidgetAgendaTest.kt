package io.github.quezka.quire

import io.github.quezka.quire.domain.ClassSlot
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.WidgetAgenda
import io.github.quezka.quire.domain.WidgetEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime

class WidgetAgendaTest {
    private val saturday = LocalDate.of(2026, 9, 26)
    private fun at(h: Int, m: Int = 0, day: LocalDate = saturday) = LocalDateTime.of(day, java.time.LocalTime.of(h, m))
    private fun build(now: LocalDateTime, events: List<Event> = emptyList(), tasks: List<Task> = emptyList(),
                      courses: List<Course> = emptyList()) =
        WidgetAgenda.build(now, courses, events, emptyList(), emptyList(), tasks)

    @Test fun todayHidesWhatEndedButKeepsWhatIsRunning() {
        val events = listOf(Event("a", saturday, 8 * 60, 9 * 60, "Early"),
            Event("b", saturday, 9 * 60, 11 * 60, "Running"), Event("c", saturday, 15 * 60, 16 * 60, "Later"))
        val days = build(at(10), events)
        val titles = days.single().entries.map { (it as WidgetEntry.Timed).item.title }
        assertEquals(listOf("Running", "Later"), titles)
    }

    @Test fun emptyDaysAreLeftOutAndFarDaysNotShown() {
        val events = listOf(Event("a", saturday.plusDays(2), 600, 660, "Soon"),
            Event("b", saturday.plusDays(20), 600, 660, "Far"))
        assertEquals(listOf(saturday.plusDays(2)), build(at(8), events).map { it.day })
    }

    @Test fun overdueTasksSitUnderTodayBeforeTheTimeline() {
        val tasks = listOf(Task("t1", "Late", due = saturday.minusDays(3)), Task("t2", "Done", due = saturday, done = true),
            Task("t3", "Tomorrow", due = saturday.plusDays(1)), Task("t4", "No date"))
        val events = listOf(Event("e", saturday, 15 * 60, 16 * 60, "Lab"))
        val days = build(at(8), events, tasks)
        val today = days[0].entries
        assertTrue((today[0] as WidgetEntry.Due).overdue)
        assertEquals("Late", (today[0] as WidgetEntry.Due).task.title)
        assertTrue(today[1] is WidgetEntry.Timed)
        assertEquals(listOf("Tomorrow"), days[1].entries.map { (it as WidgetEntry.Due).task.title })
    }

    @Test fun classesRepeatEachWeek() {
        val maths = Course("m", "Maths", slots = listOf(ClassSlot(saturday.plusDays(1).dayOfWeek.value - 1, 480, 540)))
        val days = build(at(8), courses = listOf(maths))
        assertEquals(listOf(saturday.plusDays(1)), days.map { it.day }) // next week's is beyond the 7 days
    }

    @Test fun listIsCapped() {
        val tasks = (1..50).map { Task("t$it", "Task $it", due = saturday) }
        assertEquals(WidgetAgenda.MAX_ENTRIES, build(at(8), tasks = tasks).sumOf { it.entries.size })
    }
}
