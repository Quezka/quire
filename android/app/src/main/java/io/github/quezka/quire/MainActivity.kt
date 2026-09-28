package io.github.quezka.quire

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import io.github.quezka.quire.ui.NoteEditor
import io.github.quezka.quire.ui.NotesScreen
import io.github.quezka.quire.ui.QuireTheme
import io.github.quezka.quire.ui.SettingsScreen
import io.github.quezka.quire.ui.TaskEditor
import io.github.quezka.quire.ui.TasksScreen
import io.github.quezka.quire.ui.TodayScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = container
        setContent {
            QuireTheme {
                val version by container.repository.version.collectAsState()
                var tab by rememberSaveable { mutableStateOf(0) }
                var openNote by rememberSaveable { mutableStateOf<String?>(null) }
                var editingTask by rememberSaveable { mutableStateOf<String?>(null) }
                var newTask by rememberSaveable { mutableStateOf(false) }

                val note = openNote
                if (note != null) {
                    Scaffold { padding ->
                        Box(Modifier.padding(padding)) {
                            NoteEditor(container.repository, version, note) { openNote = null }
                        }
                    }
                    return@QuireTheme
                }
                Scaffold(bottomBar = {
                    NavigationBar {
                        val tabs = listOf(
                            Triple(R.string.nav_today, Icons.Filled.Today, 0),
                            Triple(R.string.nav_tasks, Icons.Filled.CheckCircle, 1),
                            Triple(R.string.nav_notes, Icons.AutoMirrored.Filled.Notes, 2),
                            Triple(R.string.nav_settings, Icons.Filled.Settings, 3),
                        )
                        for ((label, icon, index) in tabs) {
                            NavigationBarItem(selected = tab == index, onClick = { tab = index },
                                icon = { Icon(icon, null) }, label = { Text(stringResource(label)) })
                        }
                    }
                }) { padding ->
                    Box(Modifier.padding(padding)) {
                        when (tab) {
                            0 -> TodayScreen(container.repository, version) { editingTask = it }
                            1 -> TasksScreen(container.repository, version) { uid ->
                                if (uid == null) newTask = true else editingTask = uid
                            }
                            2 -> NotesScreen(container.repository, version) { openNote = it }
                            else -> SettingsScreen(container.sync)
                        }
                    }
                }
                val task = editingTask
                if (task != null || newTask) {
                    TaskEditor(container.repository, task, defaultDue = null) {
                        editingTask = null; newTask = false
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        container.sync.syncNow() // pick up what changed on the computer
    }
}
