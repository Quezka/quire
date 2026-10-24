package io.github.quezka.quire

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.ClassSlot
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.Quiet
import io.github.quezka.quire.domain.QuietSettings
import io.github.quezka.quire.domain.Routine
import io.github.quezka.quire.sync.MemorySettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime

class QuietTest {
    private val today = LocalDate.of(2026, 9, 23) // a Wednesday
    private fun at(hour: Int, minute: Int = 0, days: Long = 0) = today.plusDays(days).atTime(hour, minute)
    private fun repo() = Repository(Records(MemoryRowStore()), today = { today }, now = { today.atTime(10, 0) })

    @Test fun touchingAndOverlappingPeriodsJoin() {
        val joined = Quiet.merge(listOf(at(9) to at(10), at(10) to at(11), at(13) to at(14), at(13, 30) to at(15)))
        assertEquals(listOf(at(9) to at(11), at(13) to at(15)), joined)
        assertEquals(at(11), Quiet.status(joined, at(10, 30)).until)
        val after = Quiet.status(joined, at(11, 30))
        assertFalse(after.active); assertEquals(at(13), after.nextStart)
        assertNull(Quiet.status(emptyList(), at(8)).nextStart)
    }

    @Test fun onlyChosenKindsCountAndMilestonesNever() {
        val repo = repo()
        repo.saveEvent(Event(Codec.newUid(), today, 9 * 60, 11 * 60, "Dentist"))
        repo.saveEvent(Event(Codec.newUid(), today, 10 * 60, 10 * 60 + 1, "Take meds"))
        repo.saveRoutine(Routine(Codec.newUid(), "Wake up", 10 * 60))
        repo.saveCourse(Course(Codec.newUid(), "Maths", slots = listOf(ClassSlot(2, 10 * 60, 11 * 60))))
        val itemsOn = { d: LocalDate -> repo.day(d).items }
        val now = at(10, 15)

        assertTrue(Quiet.periods(now, QuietSettings(true, classes = false, events = false), itemsOn).isEmpty())
        val classesOnly = Quiet.periods(now, QuietSettings(true, classes = true, events = false), itemsOn)
        assertEquals(listOf(at(10) to at(11)), classesOnly)
        val both = Quiet.periods(now, QuietSettings(true, classes = true, events = true), itemsOn)
        assertEquals(listOf(at(9) to at(11)), both) // the class and the dentist overlap into one
    }

    @Test fun settingsSurviveSavingAndStartOff() {
        val store = MemorySettings()
        assertFalse(QuietSettings.load(store).enabled)
        QuietSettings(enabled = true, classes = false, events = true, shifts = true).save(store)
        assertEquals(QuietSettings(true, false, true, true), QuietSettings.load(store))
    }
}
