package io.github.quezka.quire

import android.graphics.Bitmap
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CalendarViewWeek
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SyncRecord
import io.github.quezka.quire.domain.Absence
import io.github.quezka.quire.domain.AbsenceKind
import io.github.quezka.quire.domain.Grade
import io.github.quezka.quire.domain.Lesson
import io.github.quezka.quire.domain.RegisterData
import io.github.quezka.quire.school.RegisterStore
import io.github.quezka.quire.sync.MemorySettings
import io.github.quezka.quire.ui.FocusScreen
import io.github.quezka.quire.ui.MoreScreen
import io.github.quezka.quire.ui.NotesScreen
import io.github.quezka.quire.ui.SchoolScreen
import io.github.quezka.quire.ui.SettingsScreen
import io.github.quezka.quire.ui.WeekScreen
import io.github.quezka.quire.ui.WorkScreen
import io.github.quezka.quire.ui.QuireTheme
import io.github.quezka.quire.ui.TasksScreen
import io.github.quezka.quire.ui.TodayScreen
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.time.LocalDate

/** Renders screens with the desktop's demo data to build/screenshots (set SCREENSHOTS=1). */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w400dp-h860dp-xxhdpi", application = android.app.Application::class)
class ScreenshotTest {
    @get:Rule val compose = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private val today = LocalDate.of(2026, 9, 23)

    private fun repo(): Repository {
        val text = javaClass.classLoader!!.getResource("desktop_records.json")!!.readText()
        val records = Records(MemoryRowStore())
        records.apply(Json.parseToJsonElement(text).jsonArray.map {
            val o = it.jsonObject
            fun s(k: String) = (o[k] as JsonPrimitive).content
            SyncRecord(s("kind"), s("uid"), s("modified"),
                (o["deleted"] as JsonPrimitive).booleanOrNull ?: false, o["data"] as? JsonObject)
        })
        return Repository(records, today = { today })
    }

    @Composable
    private fun Shell(tab: Int, content: @Composable () -> Unit) = QuireTheme {
        Scaffold(bottomBar = {
            NavigationBar {
                listOf(R.string.nav_today to Icons.Filled.Today, R.string.nav_week to Icons.Filled.CalendarViewWeek,
                    R.string.nav_tasks to Icons.Filled.CheckCircle, R.string.nav_notes to Icons.AutoMirrored.Filled.Notes,
                    R.string.nav_more to Icons.Filled.GridView)
                    .forEachIndexed { i, (label, icon) ->
                        NavigationBarItem(selected = i == tab, onClick = {}, icon = { Icon(icon, null) },
                            label = { Text(androidx.compose.ui.res.stringResource(label)) })
                    }
            }
        }) { padding -> Box(Modifier.padding(padding)) { content() } }
    }

    private fun shoot(name: String) {
        if (System.getenv("SCREENSHOTS") == null) return
        compose.waitForIdle()
        val view = compose.activity.window.decorView
        val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        view.draw(android.graphics.Canvas(bitmap))
        val out = File("build/screenshots").apply { mkdirs() }.resolve("$name.png")
        out.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun container(): Container {
        val repo = repo()
        val settings = MemorySettings()
        val c = Container(compose.activity, Records(MemoryRowStore()), repo, settings)
        settings.set("school.username", "S1234567X")
        RegisterStore(settings).save(RegisterData(
            student = "Arsenii", lastSync = "2026-09-23T07:40:00",
            grades = listOf(
                Grade("1", "Matematica", today.minusDays(3), "7½", 7.5, "Scritto"),
                Grade("2", "Matematica", today.minusDays(12), "6-", 5.75, "Orale"),
                Grade("3", "Informatica", today.minusDays(5), "9", 9.0, "Pratico"),
                Grade("4", "Inglese", today.minusDays(8), "5", 5.0, "Scritto"),
                Grade("5", "Storia", today.minusDays(2), "8", 8.0, "Orale")),
            absences = listOf(
                Absence("a1", today.minusDays(15), AbsenceKind.ABSENT, justified = true, reason = "Altri motivi"),
                Absence("a2", today.minusDays(1), AbsenceKind.EARLY_EXIT, justified = true, reason = "Famiglia")),
            lessons = listOf(Lesson("l1", today.minusDays(1), "Informatica", "Normalizzazione dei database", "Neri", 2)),
        ))
        return c
    }

    @Test fun today() {
        val repo = repo()
        compose.setContent { Shell(0) { TodayScreen(repo, 0, {}, {}) } }
        shoot("today")
    }

    @Test fun week() {
        val repo = repo()
        compose.setContent { Shell(1) { WeekScreen(repo, 0) {} } }
        shoot("week")
    }

    @Test fun tasks() {
        val repo = repo()
        compose.setContent { Shell(2) { TasksScreen(repo, 0) {} } }
        shoot("tasks")
    }

    @Test fun notes() {
        val repo = repo()
        compose.setContent { Shell(3) { NotesScreen(repo, 0) {} } }
        shoot("notes")
    }

    @Test fun more() {
        val c = container()
        compose.setContent { Shell(4) { MoreScreen(c) {} } }
        shoot("more")
    }

    @Test fun work() {
        val repo = repo()
        compose.setContent { Shell(4) { WorkScreen(repo, 0) {} } }
        shoot("work")
    }

    @Test fun focus() {
        val c = container()
        compose.setContent { Shell(4) { FocusScreen(c, 0) {} } }
        shoot("focus")
    }

    @Test fun school() {
        val c = container()
        compose.setContent { Shell(4) { SchoolScreen(c, 0) {} } }
        shoot("school")
    }

    @Test fun settings() {
        val c = container()
        compose.setContent { Shell(4) { SettingsScreen(c) {} } }
        shoot("settings")
    }
}
