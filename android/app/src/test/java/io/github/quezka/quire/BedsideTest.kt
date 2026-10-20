package io.github.quezka.quire

import io.github.quezka.quire.domain.Bedside
import io.github.quezka.quire.domain.ClassSlot
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.TaskKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

class BedsideTest {
    private val tuesday = LocalDate.of(2026, 10, 20)
    private fun at(h: Int, m: Int = 0, day: LocalDate = tuesday) = LocalDateTime.of(day, LocalTime.of(h, m))
    private fun build(
        now: LocalDateTime,
        events: List<Event> = emptyList(),
        tasks: List<Task> = emptyList(),
        courses: List<Course> = emptyList(),
        jobs: List<Job> = emptyList(),
        shifts: List<Shift> = emptyList(),
    ) = Bedside.build(now, courses, events, jobs, shifts, tasks)

    @Test fun nextIsWhatRunsOrComesNextToday() {
        val events = listOf(
            Event("a", tuesday, 8 * 60, 9 * 60, "Over"),
            Event("b", tuesday, 9 * 60, 11 * 60, "Running"),
            Event("c", tuesday, 15 * 60, 16 * 60, "Later"),
        )
        assertEquals("Running", build(at(10), events).next?.title)
        assertEquals("Later", build(at(12), events).next?.title)
        assertNull(build(at(17), events).next)
    }

    @Test fun nextCarriesAbsoluteTimesForTheCountdown() {
        val next = build(at(7), listOf(Event("a", tuesday, 9 * 60 + 30, 10 * 60, "Lab"))).next!!
        assertEquals(at(9, 30), next.start)
        assertEquals(at(10), next.end)
        assertEquals(ItemKind.EVENT, next.kind)
    }

    @Test fun tomorrowFirstIsTheEarliestStart() {
        val tomorrow = tuesday.plusDays(1)
        val events = listOf(Event("a", tomorrow, 14 * 60, 15 * 60, "Afternoon"), Event("b", tomorrow, 8 * 60, 9 * 60, "Morning"))
        assertEquals("Morning", build(at(22), events).tomorrowFirst?.title)
        assertEquals(at(8, 0, tomorrow), build(at(22), events).tomorrowFirst?.start)
    }

    @Test fun classesCountTomorrowToo() {
        val tomorrow = tuesday.plusDays(1)
        val maths = Course("m", "Matematica", slots = listOf(ClassSlot(tomorrow.dayOfWeek.value - 1, 8 * 60, 9 * 60)))
        val feed = build(at(22), courses = listOf(maths))
        assertEquals("Matematica", feed.tomorrowFirst?.title)
        assertEquals(ItemKind.CLASS, feed.tomorrowFirst?.kind)
    }

    @Test fun theTailOfTonightsShiftIsNotTomorrowsStart() {
        // A shift from 22:00 for 8 hours runs into tomorrow morning; that is not something that starts then.
        val job = Job("j", "Bar", patterns = listOf(ShiftPattern(tuesday.dayOfWeek.value - 1, 22 * 60, 8 * 60)))
        val feed = build(at(18), jobs = listOf(job))
        assertEquals("Bar", feed.next?.title)
        assertNull(feed.tomorrowFirst)
    }

    @Test fun tasksAreCountedByDueDay() {
        val tomorrow = tuesday.plusDays(1)
        val tasks = listOf(
            Task("t1", "Late", due = tuesday.minusDays(2)),
            Task("t2", "Today", due = tuesday),
            Task("t3", "Done", due = tuesday, done = true),
            Task("t4", "Tomorrow", due = tomorrow),
            Task("t5", "Later", due = tuesday.plusDays(5)),
            Task("t6", "No date"),
        )
        val feed = build(at(8), tasks = tasks)
        assertEquals(2, feed.tasksToday)
        assertEquals(1, feed.tasksTomorrow)
        assertEquals("Late", feed.nextTask?.title)
    }

    @Test fun anExamComesBeforeOtherTasksDueTheSameDay() {
        val tasks = listOf(Task("a", "Homework", TaskKind.HOMEWORK, due = tuesday), Task("b", "Zeta exam", TaskKind.EXAM, due = tuesday))
        assertEquals("Zeta exam", build(at(8), tasks = tasks).nextTask?.title)
    }

    @Test fun emptyDayGivesAnEmptyFeed() {
        val feed = build(at(8))
        assertNull(feed.next)
        assertNull(feed.tomorrowFirst)
        assertNull(feed.nextTask)
        assertEquals(0, feed.tasksToday)
    }
}
