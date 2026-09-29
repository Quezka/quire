package io.github.quezka.quire

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.filled.CalendarViewWeek
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import io.github.quezka.quire.ui.CoursesScreen
import io.github.quezka.quire.ui.FocusScreen
import io.github.quezka.quire.ui.MoreScreen
import io.github.quezka.quire.ui.Motion
import io.github.quezka.quire.ui.Motion.push
import io.github.quezka.quire.ui.NoteEditor
import io.github.quezka.quire.ui.NotesScreen
import io.github.quezka.quire.ui.QuireTheme
import io.github.quezka.quire.ui.SchoolScreen
import io.github.quezka.quire.ui.SettingsScreen
import io.github.quezka.quire.ui.TaskEditor
import io.github.quezka.quire.ui.TasksScreen
import io.github.quezka.quire.ui.TodayScreen
import io.github.quezka.quire.ui.WeekScreen
import io.github.quezka.quire.ui.WorkScreen
import java.time.LocalDate

/** Pages reached from the More tab. */
enum class Page { SCHOOL, WORK, FOCUS, COURSES, SETTINGS }

class MainActivity : ComponentActivity() {
    companion object {
        // Tabs are 0-4; 10 + a Page's position opens that page under More.
        const val TAB_SCHOOL = 10
        const val TAB_FOCUS = 12
    }

    private var requested by mutableStateOf<Int?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        requested = intent?.getIntExtra("tab", -1)?.takeIf { it >= 0 }
        val container = container
        setContent {
            QuireTheme {
                val version by container.repository.version.collectAsState()
                var tab by rememberSaveable { mutableStateOf(0) }
                var page by rememberSaveable { mutableStateOf<Page?>(null) }
                var openNote by rememberSaveable { mutableStateOf<String?>(null) }
                var editingTask by rememberSaveable { mutableStateOf<String?>(null) }
                var newTaskDue by rememberSaveable { mutableStateOf<LocalDate?>(null) }
                var newTask by rememberSaveable { mutableStateOf(false) }

                // Opened from a notification: go where it points.
                LaunchedEffect(requested) {
                    when (val r = requested) {
                        null -> Unit
                        in 0..4 -> { tab = r; page = null }
                        else -> { tab = 4; page = Page.entries[r - 10] }
                    }
                    requested = null
                }
                AskForNotifications()

                AnimatedContent(openNote, transitionSpec = { push(forward = targetState != null) },
                    label = "note") { note ->
                    if (note != null) {
                        Scaffold { padding ->
                            Box(Modifier.padding(padding)) {
                                NoteEditor(container.repository, version, note) { openNote = null }
                            }
                        }
                    } else {
                        Scaffold(bottomBar = {
                            NavigationBar {
                                val tabs = listOf(
                                    Triple(R.string.nav_today, Icons.Filled.Today, 0),
                                    Triple(R.string.nav_week, Icons.Filled.CalendarViewWeek, 1),
                                    Triple(R.string.nav_tasks, Icons.Filled.CheckCircle, 2),
                                    Triple(R.string.nav_notes, Icons.AutoMirrored.Filled.Notes, 3),
                                    Triple(R.string.nav_more, Icons.Filled.GridView, 4),
                                )
                                for ((label, icon, index) in tabs) {
                                    NavigationBarItem(selected = tab == index,
                                        onClick = { if (tab == index) page = null; tab = index },
                                        icon = { Icon(icon, null) }, label = { Text(stringResource(label)) })
                                }
                            }
                        }) { padding ->
                            Box(Modifier.padding(padding).fillMaxSize()) {
                                AnimatedContent(tab, transitionSpec = { Motion.tabs() }, label = "tab") { shown ->
                                    when (shown) {
                                        0 -> TodayScreen(container.repository, version,
                                            openTask = { editingTask = it },
                                            newTask = { newTaskDue = it; newTask = true })
                                        1 -> WeekScreen(container.repository, version) { editingTask = it }
                                        2 -> TasksScreen(container.repository, version) { uid ->
                                            if (uid == null) { newTaskDue = null; newTask = true } else editingTask = uid
                                        }
                                        3 -> NotesScreen(container.repository, version) { openNote = it }
                                        else -> MorePages(container, version, page) { page = it }
                                    }
                                }
                            }
                        }
                    }
                }
                val task = editingTask
                if (task != null || newTask) {
                    TaskEditor(container.repository, task, defaultDue = if (newTask) newTaskDue else null) {
                        editingTask = null; newTask = false
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        requested = intent.getIntExtra("tab", -1).takeIf { it >= 0 }
    }

    override fun onResume() {
        super.onResume()
        container.sync.syncNow() // pick up what changed on the computer
        container.focus.tick(announce = false)
        container.reminders.plan()
    }
}

@Composable
private fun MorePages(container: Container, version: Int, page: Page?, open: (Page?) -> Unit) {
    BackHandler(enabled = page != null) { open(null) }
    AnimatedContent(page, transitionSpec = { push(forward = targetState != null) }, label = "page") { shown ->
        val back = { open(null) }
        when (shown) {
            null -> MoreScreen(container, open)
            Page.SCHOOL -> SchoolScreen(container, version, back)
            Page.WORK -> WorkScreen(container.repository, version, back)
            Page.FOCUS -> FocusScreen(container, version, back)
            Page.COURSES -> CoursesScreen(container.repository, version, back)
            Page.SETTINGS -> SettingsScreen(container, back)
        }
    }
}

/** Once, on Android 13+: ask to show notifications (reminders, focus, school news). */
@Composable
private fun AskForNotifications() {
    if (Build.VERSION.SDK_INT < 33) return
    var asked by rememberSaveable { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) {
        if (!asked) {
            asked = true
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}
