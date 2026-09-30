package io.github.quezka.quire

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SyncRecord
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.TaskKind
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/** The phone must read exactly what the desktop writes (records exported from its demo data). */
class CompatibilityTest {
    private val today = LocalDate.of(2026, 9, 23) // the desktop fixture's fixed clock

    private fun desktopRecords(): List<SyncRecord> {
        val text = javaClass.classLoader!!.getResource("desktop_records.json")!!.readText()
        return Json.parseToJsonElement(text).jsonArray.map {
            val o = it.jsonObject
            fun s(k: String) = (o[k] as JsonPrimitive).content
            SyncRecord(s("kind"), s("uid"), s("modified"),
                (o["deleted"] as JsonPrimitive).booleanOrNull ?: false, o["data"] as? JsonObject)
        }
    }

    private fun repository(): Repository {
        val records = Records(MemoryRowStore())
        records.apply(desktopRecords())
        return Repository(records, today = { today })
    }

    @Test fun everyDesktopKindIsRead() {
        val repo = repository()
        assertEquals(6, repo.courses().size)
        val maths = repo.courses().first { it.name == "Mathematics" }
        assertEquals(listOf(0, 2, 4), maths.slots.map { it.weekday })
        assertEquals("B12", maths.roomFor(maths.slots[0]))

        val tasks = repo.tasks()
        assertEquals(8, tasks.size)
        val homework = tasks.first { it.title == "Problem set 3 (q1–12)" }
        assertEquals(TaskKind.HOMEWORK, homework.kind)
        assertEquals(maths.uid, homework.courseUid) // references are uids, like the desktop's
        assertEquals(today.plusDays(1), homework.due)
        assertTrue(tasks.any { it.done })

        val notes = repo.notes()
        assertEquals(5, notes.size)
        assertTrue(notes.first().pinned) // "Ideas" is pinned on the desktop
        assertTrue(notes.any { it.topic == "Cell biology" && it.courseUid != null })

        assertEquals("Remember the permission slip", repo.journal(today))
        assertEquals(2, repo.jobs().size)
        assertTrue(repo.jobs().any { it.patterns.isNotEmpty() && it.hourlyRate == 8.5 })
    }

    @Test fun todayLooksLikeTheDesktopsToday() {
        val day = repository().day(today) // a Wednesday
        val classes = day.items.filter { it.kind == ItemKind.CLASS }.map { it.title }
        assertEquals(listOf("Mathematics", "Chemistry", "PE"), classes)
        assertTrue(day.items.any { it.kind == ItemKind.EVENT && it.title == "Lunch with Sam" })
        assertTrue(day.tasks.any { it.title == "Titration pre-lab questions" }) // overdue
    }

    @Test fun savingFromThePhoneKeepsFieldsItDoesNotShow() {
        val records = Records(MemoryRowStore())
        records.apply(desktopRecords())
        val repo = Repository(records, today = { today })
        val course = desktopRecords().first { it.kind == "course" }
        val withExtra = course.copy(modified = "2027-01-01T00:00:00.000Z",
            data = JsonObject(course.data!! + ("future_field" to JsonPrimitive("kept"))))
        records.apply(listOf(withExtra))
        val task = repo.tasks().first()
        repo.saveTask(task.copy(title = "Edited on the phone"))
        val saved = records.get("task", task.uid)!!.data!!
        assertEquals("Edited on the phone", (saved["title"] as JsonPrimitive).content)
        // Same keys as the desktop writes, nothing lost.
        assertEquals(desktopRecords().first { it.uid == task.uid }.data!!.keys, saved.keys)
        val stored = records.get("course", course.uid)!!.data!!
        assertEquals("kept", (Codec.courseData(Codec.course(records.get("course", course.uid)!!), stored)
            ["future_field"] as JsonPrimitive).content)
    }

    @Test fun desktopPicturesAreRead() {
        val png = repository().image("5b5bd6f5a5244e0c9d1b7f3e2a1c0d9e")!!
        assertEquals(0x89.toByte(), png[0])
        assertEquals("PNG", String(png, 1, 3))
        assertEquals(null, repository().image("0000000000000000"))
        assertEquals("Schema", io.github.quezka.quire.domain.deriveNoteTitle(
            "![](quire-image:5b5bd6f5a5244e0c)\n# Schema\n![ER](quire-image:5b5bd6f5a5244e0c)"))
    }
}
