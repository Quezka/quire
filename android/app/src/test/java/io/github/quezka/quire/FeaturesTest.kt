package io.github.quezka.quire

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SyncRecord
import io.github.quezka.quire.domain.AbsenceKind
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.FocusSettings
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Phase
import io.github.quezka.quire.domain.PomodoroTimer
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.Work
import io.github.quezka.quire.domain.formatMark
import io.github.quezka.quire.domain.neededGrade
import io.github.quezka.quire.focus.FocusController
import io.github.quezka.quire.notify.ReminderPlan
import io.github.quezka.quire.notify.ReminderSettings
import io.github.quezka.quire.school.Classeviva
import io.github.quezka.quire.school.PlainBox
import io.github.quezka.quire.school.RegisterStore
import io.github.quezka.quire.school.SchoolSync
import io.github.quezka.quire.sync.DeviceLink
import io.github.quezka.quire.sync.MemorySettings
import io.github.quezka.quire.update.newer
import io.github.quezka.quire.update.parseRelease
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.util.Base64

class FeaturesTest {
    private val today = LocalDate.of(2026, 9, 23) // a Wednesday
    private fun repo(records: Records = Records(MemoryRowStore())) =
        Repository(records, today = { today }, now = { today.atTime(10, 0) })

    // ---- work ----

    @Test fun payAndSummaryMatchTheDesktop() {
        val repo = repo()
        val job = repo.saveJob(Job(Codec.newUid(), "Pizzeria", hourlyRate = 8.5, deductions = 10.0),
            listOf(ShiftPattern(4, 19 * 60, 5 * 60, 30))) // Fridays 19-24, half an hour unpaid
        repo.saveShift(Shift(null, job.uid, today, 18 * 60, 4 * 60 + 30))
        val week = repo.workWeek()
        assertEquals(2, week.shifts)
        assertEquals(4 * 60 + 30 + 4 * 60 + 30, week.minutes)
        assertEquals(76.5, week.pay!!, 0.001)
        assertEquals(68.85, week.net!!, 0.001)
    }

    @Test fun changingTheWeeklyScheduleKeepsPastWeeks() {
        val monday = LocalDate.of(2026, 9, 21)
        val old = ShiftPattern(0, 9 * 60, 60, since = LocalDate.of(2026, 9, 1))
        val new = ShiftPattern(1, 10 * 60, 60)
        val result = Work.reschedule(listOf(old), listOf(new), monday)
        assertEquals(listOf(old.copy(until = monday.minusDays(1)), new.copy(since = monday)), result)
    }

    @Test fun skippingAWeeklyOccurrenceRemovesJustThatOne() {
        val repo = repo()
        val job = repo.saveJob(Job(Codec.newUid(), "Café"), listOf(ShiftPattern(today.dayOfWeek.value - 1, 8 * 60, 120)))
        assertEquals(1, repo.day(today).items.count { it.kind == ItemKind.SHIFT && it.weekly })
        repo.skipOccurrence(job.uid, today, 8 * 60)
        assertEquals(0, repo.day(today).items.count { it.kind == ItemKind.SHIFT })
        assertEquals(1, repo.day(today.plusWeeks(1)).items.count { it.kind == ItemKind.SHIFT })
    }

    @Test fun jobsAndShiftsSaveInTheDesktopFormat() {
        val job = Job("j1", "Café", "#30a46c", 9.0, 5.0, listOf(ShiftPattern(2, 480, 240, 15, today, null)),
            setOf(today to 480))
        val data = Codec.jobData(job, null)
        assertEquals(job, Codec.job(SyncRecord("job", "j1", "x", data = data)))
        val shift = Shift("s1", "j1", today, 1320, 240, 30, "night")
        assertEquals(shift, Codec.shift(SyncRecord("shift", "s1", "x", data = Codec.shiftData(shift, null))))
        assertEquals("[2,480,240,15,\"2026-09-23\",null]", data["patterns"].toString().removeSurrounding("[", "]"))
    }

    // ---- focus ----

    @Test fun theTimerRunsThroughPhasesAgainstTheClock() {
        val t0 = Instant.parse("2026-09-23T10:00:00Z")
        val timer = PomodoroTimer(FocusSettings(25, 5, 15, 2, autoContinue = true))
        timer.start(t0)
        assertNull(timer.tick(t0.plusSeconds(60)))
        val ended = timer.tick(t0 + Duration.ofMinutes(25))!!
        assertEquals(Phase.WORK, ended.phase)
        assertEquals(Phase.SHORT_BREAK, timer.phase)
        assertTrue(timer.running)
        timer.pause(t0 + Duration.ofMinutes(27))
        assertEquals(Duration.ofMinutes(3), timer.remaining(t0 + Duration.ofHours(5)))
    }

    @Test fun finishedFocusSessionsAreLoggedEvenAfterTheAppWasClosed() {
        val repo = repo()
        var now = Instant.parse("2026-09-23T10:00:00Z")
        val settings = MemorySettings()
        val focus = FocusController(repo, settings, null) { now }
        val task = repo.saveTask(Task(Codec.newUid(), "Revise chemistry"))
        focus.focusOn(task.uid)
        focus.toggle()
        now = now.plus(Duration.ofMinutes(26))
        // A fresh controller (the app restarted) picks the timer up from its saved state.
        val restarted = FocusController(repo, settings, null) { now }
        restarted.tick(announce = false)
        val logged = repo.focusSessions().single()
        assertEquals(25, logged.minutes)
        assertEquals(task.uid, logged.taskUid)
        assertEquals("Revise chemistry", logged.label)
        val started = (Codec.focusData(logged)["started"] as JsonPrimitive).content
        assertEquals(LocalDateTime.ofInstant(Instant.parse("2026-09-23T10:00:00Z"), java.time.ZoneId.systemDefault()),
            LocalDateTime.parse(started))
        assertEquals(19, started.length) // seconds included, like the desktop's
    }

    // ---- reminders ----

    @Test fun remindersComeBeforeWhatTheSettingsAskFor() {
        val repo = repo()
        repo.saveEvent(Event("e1", today, 11 * 60, 12 * 60, "Dentist"))
        repo.saveCourse(Course("c1", "Maths", slots = listOf(io.github.quezka.quire.domain.ClassSlot(2, 10 * 60 + 30, 11 * 60 + 20))))
        val now = today.atTime(10, 0)
        val plan = ReminderPlan.upcoming(ReminderSettings(), now, { repo.day(it).items })
        assertEquals(listOf("Dentist"), plan.map { it.item.title }) // classes are off by default
        assertEquals(today.atTime(10, 50), plan.single().at)
        val withClasses = ReminderPlan.upcoming(ReminderSettings(classes = true), now, { repo.day(it).items })
        assertEquals(listOf("Maths", "Dentist"), withClasses.map { it.item.title })
        assertTrue(ReminderPlan.upcoming(ReminderSettings(minutesBefore = null), now, { repo.day(it).items }).isEmpty())
    }

    // ---- school ----

    private fun canned(responses: Map<String, String>): Classeviva = Classeviva({ method, url, _, _ ->
        val path = url.removePrefix(Classeviva.BASE)
        val key = responses.keys.firstOrNull { path.startsWith(it) || path.contains(it) }
        if (key == null) 404 to "{}" else 200 to responses.getValue(key)
    }, today = { today })

    private val login = """{"token":"t","ident":"S1234567X","firstName":"ARSENII","lastName":"DOMASHENKO"}"""

    @Test fun anEarlyExitWithoutAnHourIsReadAndTheHourYouEnterStays() {
        // Exactly what Classeviva sent for the real early exit on 28 September.
        val absences = """{"events":[{"evtId":12720496,"evtCode":"ABU0","evtDate":"2026-09-28","evtHPos":null,
            "evtValue":null,"isJustified":true,"justifReasonCode":"B","justifReasonDesc":"Famiglia",
            "hoursAbsence":[],"webJustifStatus":0},
            {"evtId":2,"evtCode":"ABR0","evtDate":"2026-09-22","evtHPos":"2","isJustified":false}]}"""
        val register = canned(mapOf("/auth/login" to login, "/absences/details" to absences))
        val settings = MemorySettings()
        val repo = repo()
        val school = SchoolSync(register, repo, RegisterStore(settings), settings, PlainBox())
        school.connect("S1234567X", "secret")
        school.apply(school.fetch())
        val exit = school.data().absences.first { it.kind == AbsenceKind.EARLY_EXIT }
        assertNull(exit.hour)
        assertTrue(exit.needsHour)
        assertEquals(2, school.data().absences.first { it.kind == AbsenceKind.LATE }.hour) // a string is fine too

        school.setAbsenceHour(exit.id, 4)
        school.apply(school.fetch()) // the register still has no hour: yours stays
        val again = school.data().absences.first { it.kind == AbsenceKind.EARLY_EXIT }
        assertEquals(4, again.knownHour)
        assertTrue(again.hourIsYours)
    }

    @Test fun homeworkBecomesTasksAndSubjectsCourses() {
        val register = canned(mapOf(
            "/auth/login" to login,
            "/subjects" to """{"subjects":[{"id":7,"description":"MATEMATICA","teachers":[{"teacherName":"ROSSI MARIO"}]}]}""",
            "/agenda/all" to """{"agenda":[{"evtId":1,"evtCode":"AGNT","evtDatetimeBegin":"2026-09-25T08:00:00+02:00",
                "notes":"Verifica sulle derivate","subjectId":7,"subjectDesc":"MATEMATICA","authorName":"ROSSI MARIO"}]}""",
            "/grades" to """{"grades":[{"evtId":9,"evtDate":"2026-09-20","subjectId":7,"subjectDesc":"MATEMATICA",
                "displayValue":"7½","decimalValue":7.5,"componentDesc":"Scritto"}]}""",
        ))
        val settings = MemorySettings()
        val repo = repo()
        val school = SchoolSync(register, repo, RegisterStore(settings), settings, PlainBox())
        assertEquals("Arsenii Domashenko", school.connect("S1234567X", "pw"))
        school.apply(school.fetch())
        val course = repo.courses().single()
        assertEquals("Matematica", course.name)
        assertEquals("Rossi Mario", course.teacher)
        val task = repo.tasks().single()
        assertEquals("Verifica sulle derivate", task.title)
        assertEquals(io.github.quezka.quire.domain.TaskKind.EXAM, task.kind)
        assertEquals(course.uid, task.courseUid)
        assertEquals("classeviva:agenda:1", task.externalId)
        assertEquals("7½", school.data().grades.single().display)
        // A second sync changes nothing.
        school.apply(school.fetch())
        assertEquals(1, repo.tasks().size)
    }

    @Test fun anImportMadeOnBothDevicesShowsOnce() {
        val records = Records(MemoryRowStore())
        val repo = repo(records)
        repo.saveTask(Task("phone", "Esercizi", externalId = "classeviva:agenda:5"))
        records.apply(listOf(SyncRecord("task", "desktop", "2099-01-01T00:00:00.000Z",
            data = Codec.taskData(Task("desktop", "Esercizi pag. 4", externalId = "classeviva:agenda:5"), null))))
        assertEquals(listOf("Esercizi pag. 4"), repo.tasks().map { it.title })
        repo.deleteTask("desktop")
        assertTrue(repo.tasks().isEmpty())
    }

    @Test fun marks() {
        assertEquals("7½", formatMark(7.5))
        assertEquals("6+", formatMark(6.25))
        assertEquals("7-", formatMark(6.75))
        assertEquals(7.5, neededGrade(listOf(5.0, 5.5), 6.0), 0.0)
    }

    // ---- setup link and updates ----

    @Test fun theComputersSetupCodeIsRead() {
        val json = """{"v":"1","project":"quire-sync-1a2b3","api_key":"AIzaSyA-abcdefghijklmnopqrstu","email":"a@b.it","refresh":"r1","cv_user":"S1","cv_pass":"pw"}"""
        val link = DeviceLink.parse("quire-link:" + Base64.getUrlEncoder().withoutPadding().encodeToString(json.toByteArray()))
        assertNotNull(link)
        assertEquals("quire-sync-1a2b3", link!!.projectId)
        assertEquals("pw", link.registerPassword)
        assertNull(DeviceLink.parse("https://example.com"))
    }

    @Test fun updatesFindTheApk() {
        val release = parseRelease("""{"tag_name":"v0.16.0","body":"x","assets":[
            {"name":"quire_0.16.0_amd64.deb","browser_download_url":"d","size":1},
            {"name":"Quire-0.16.0-android.apk","browser_download_url":"https://x/a.apk","size":42}]}""")!!
        assertEquals("https://x/a.apk", release.apkUrl)
        assertTrue(newer("0.16.0", "0.15.0"))
        assertTrue(newer("0.15.10", "0.15.9"))
        assertFalse(newer("0.15.0", "0.15.0"))
    }
}
