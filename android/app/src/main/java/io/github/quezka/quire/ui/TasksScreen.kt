package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.Button
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Agenda
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.DueBucket
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.TaskKind
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

private fun bucketLabel(b: DueBucket) = when (b) {
    DueBucket.OVERDUE -> R.string.bucket_overdue
    DueBucket.TODAY -> R.string.bucket_today
    DueBucket.UPCOMING -> R.string.bucket_upcoming
    DueBucket.LATER -> R.string.bucket_later
    DueBucket.UNDATED -> R.string.bucket_undated
    DueBucket.DONE -> R.string.bucket_done
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TasksScreen(repo: Repository, version: Int, openTask: (String?) -> Unit) {
    var showDone by rememberSaveable { mutableStateOf(false) }
    val today = repo.today()
    val groups = remember(version, showDone) { Agenda.groups(repo.tasks(), today, showDone) }
    val courses = remember(version) { repo.courses().associateBy { it.uid } }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            TopAppBar(title = { Text(stringResource(R.string.nav_tasks)) }, actions = {
                FilterChip(selected = showDone, onClick = { showDone = !showDone },
                    label = { Text(stringResource(R.string.show_completed)) },
                    modifier = Modifier.padding(end = 12.dp))
            })
            if (groups.isEmpty()) {
                Box(Modifier.padding(16.dp)) { Hint(stringResource(R.string.no_tasks)) }
            }
            LazyColumn(contentPadding = PaddingValues(16.dp, 0.dp, 16.dp, 96.dp)) {
                for ((bucket, tasks) in groups) {
                    item(key = bucket.name) {
                        Text("${stringResource(bucketLabel(bucket))}  ${tasks.size}",
                            style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                            color = if (bucket == DueBucket.OVERDUE) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 14.dp, bottom = 2.dp))
                    }
                    items(tasks, key = { it.uid }) { task ->
                        TaskRow(task, courses[task.courseUid]?.name, today,
                            onCheck = { repo.setDone(task.uid, it) }, onOpen = { openTask(task.uid) })
                    }
                }
            }
        }
        FloatingActionButton(onClick = { openTask(null) },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            Icon(Icons.Filled.Add, stringResource(R.string.new_task))
        }
    }
}

/** Create (uid null) or edit a task, as a bottom sheet. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskEditor(repo: Repository, uid: String?, defaultDue: LocalDate?, close: () -> Unit) {
    val existing = remember(uid) { uid?.let(repo::task) }
    val courses = remember { repo.courses() }
    var title by remember { mutableStateOf(existing?.title.orEmpty()) }
    var kind by remember { mutableStateOf(existing?.kind ?: TaskKind.TASK) }
    var courseUid by remember { mutableStateOf(existing?.courseUid) }
    var due by remember { mutableStateOf(existing?.due ?: defaultDue) }
    var details by remember { mutableStateOf(existing?.details.orEmpty()) }
    var done by remember { mutableStateOf(existing?.done ?: false) }
    var picking by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    fun save() {
        val base = existing ?: Task(Codec.newUid(), "")
        repo.saveTask(base.copy(title = title, kind = kind, courseUid = courseUid, due = due,
            details = details, done = done))
        close()
    }

    ModalBottomSheet(onDismissRequest = close, sheetState = sheet) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)
            .verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(if (existing == null) R.string.new_task else R.string.edit_task),
                style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            OutlinedTextField(title, { title = it }, Modifier.fillMaxWidth(),
                placeholder = { Text(stringResource(R.string.task_title_hint)) },
                textStyle = MaterialTheme.typography.titleMedium)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                for (k in listOf(TaskKind.TASK, TaskKind.HOMEWORK, TaskKind.EXAM)) {
                    FilterChip(selected = kind == k, onClick = { kind = k },
                        label = { Text(stringResource(kindLabel(k))) })
                }
            }
            CoursePicker(courses, courseUid) { courseUid = it }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = { picking = true }) {
                    Text(due?.let { context.getString(R.string.due_on, relativeDate(context, it, repo.today())) }
                        ?: stringResource(R.string.no_due_date))
                }
                if (due != null) TextButton(onClick = { due = null }) { Text(stringResource(R.string.clear)) }
            }
            OutlinedTextField(details, { details = it }, Modifier.fillMaxWidth().heightIn(min = 110.dp),
                label = { Text(stringResource(R.string.details)) })
            if (existing != null) Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(done, { done = it })
                Spacer(Modifier.padding(6.dp))
                Text(stringResource(R.string.completed))
            }
            if (existing?.imported == true) Hint(stringResource(R.string.from_register))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (existing != null) TextButton(onClick = { repo.deleteTask(existing.uid); close() }) {
                    Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
                }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = close) { Text(stringResource(R.string.cancel)) }
                Button(onClick = ::save, enabled = title.isNotBlank()) { Text(stringResource(R.string.save)) }
            }
            Spacer(Modifier.height(8.dp))
        }
    }

    if (picking) {
        val state = rememberDatePickerState(
            initialSelectedDateMillis = (due ?: repo.today()).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let {
                        due = Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()
                    }
                    picking = false
                }) { Text(stringResource(R.string.ok)) }
            },
            dismissButton = { TextButton(onClick = { picking = false }) { Text(stringResource(R.string.cancel)) } },
        ) { DatePicker(state) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CoursePicker(courses: List<Course>, selected: String?, onPick: (String?) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val name = courses.firstOrNull { it.uid == selected }?.name ?: stringResource(R.string.no_course)
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(name, {}, readOnly = true, label = { Text(stringResource(R.string.course)) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor())
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            DropdownMenuItem(text = { Text(stringResource(R.string.no_course)) },
                onClick = { onPick(null); open = false })
            for (c in courses) DropdownMenuItem(text = { Text(c.name) },
                onClick = { onPick(c.uid); open = false })
        }
    }
}

@Composable
fun ConfirmDialog(text: String, confirm: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, text = { Text(text) },
        confirmButton = { TextButton(onClick = onConfirm) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}
