package io.github.quezka.quire.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Task
import kotlinx.coroutines.delay
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(repo: Repository, version: Int, openTask: (String) -> Unit) {
    val today = repo.today()
    var day by rememberSaveable { mutableStateOf(today) }
    val agenda = remember(version, day) { repo.day(day) }
    val courses = remember(version) { repo.courses().associateBy { it.uid } }
    val context = LocalContext.current

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = {
                Column {
                    Text(longDate(day, today), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (day != today) Text(relativeDate(context, day, today),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
            actions = {
                IconButton(onClick = { day = day.minusDays(1) }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, stringResource(R.string.previous_day))
                }
                if (day != today) IconButton(onClick = { day = today }) {
                    Icon(Icons.Filled.Today, stringResource(R.string.back_to_today))
                }
                IconButton(onClick = { day = day.plusDays(1) }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, stringResource(R.string.next_day))
                }
            },
        )
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp, 4.dp, 16.dp, 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item { SectionTitle(stringResource(R.string.schedule)) }
            if (agenda.items.isEmpty()) item { Hint(stringResource(R.string.nothing_scheduled)) }
            items(agenda.items, key = { "${it.kind}-${it.refUid}-${it.start}" }) { AgendaRow(it) }

            item { SectionTitle(stringResource(R.string.to_do)) }
            if (agenda.tasks.isEmpty()) item { Hint(stringResource(R.string.nothing_due)) }
            items(agenda.tasks, key = { it.uid }) { task ->
                TaskRow(task, courses[task.courseUid]?.name, today,
                    onCheck = { repo.setDone(task.uid, it) }, onOpen = { openTask(task.uid) })
            }
            item { QuickAdd(onAdd = { title -> repo.saveTask(Task(Codec.newUid(), title, due = day)) }) }

            item { SectionTitle(stringResource(R.string.day_note)) }
            item(key = "note-$day") { DayNote(repo, day, agenda.journal) }
        }
    }
}

@Composable
fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(top = 12.dp, bottom = 2.dp))
}

@Composable
fun Hint(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun AgendaRow(item: AgendaItem) {
    val kind = stringResource(when (item.kind) {
        ItemKind.CLASS -> R.string.kind_class
        ItemKind.EVENT -> R.string.kind_event
        ItemKind.SHIFT -> R.string.kind_shift
    })
    val extra = listOf(item.room, item.teacher, item.details.lineSequence().firstOrNull().orEmpty())
        .filter { it.isNotBlank() }
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        shape = RoundedCornerShape(14.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(4.dp).height(40.dp)
                .background(parseColor(item.color), RoundedCornerShape(2.dp)))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(item.title, fontWeight = FontWeight.SemiBold, maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
                val meta = buildList {
                    add(span(item.start, item.end)); add(kind); addAll(extra)
                    if (item.continues) add(stringResource(R.string.continues_from_yesterday))
                }
                Text(meta.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2,
                    overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
fun TaskRow(task: Task, course: String?, today: LocalDate, onCheck: (Boolean) -> Unit, onOpen: () -> Unit) {
    val context = LocalContext.current
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onOpen).padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = task.done, onCheckedChange = onCheck)
        Column(Modifier.weight(1f)) {
            Text(task.title, maxLines = 2, overflow = TextOverflow.Ellipsis,
                textDecoration = if (task.done) TextDecoration.LineThrough else null,
                color = if (task.isOverdue(today)) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurface)
            val due = task.due
            val meta = listOfNotNull(
                course,
                stringResource(kindLabel(task.kind)).takeIf { task.kind != io.github.quezka.quire.domain.TaskKind.TASK },
                due?.let {
                    if (task.isOverdue(today)) context.getString(R.string.was_due, relativeDateInline(context, it, today))
                    else relativeDate(context, it, today)
                },
            )
            if (meta.isNotEmpty()) Text(meta.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun QuickAdd(onAdd: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(text, { text = it }, Modifier.weight(1f),
            placeholder = { Text(stringResource(R.string.quick_add_hint)) }, singleLine = true,
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = {
                if (text.isNotBlank()) { onAdd(text); text = "" }
            }),
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                imeAction = androidx.compose.ui.text.input.ImeAction.Done))
        IconButton(onClick = { if (text.isNotBlank()) { onAdd(text); text = "" } }) {
            Icon(Icons.Filled.Add, stringResource(R.string.add))
        }
    }
}

/** Saved shortly after typing stops, and when leaving the day. Changes that arrive by sync
 *  replace the text unless it's being edited (then the edit wins, as on the desktop). */
@Composable
private fun DayNote(repo: Repository, day: LocalDate, stored: String) {
    var text by remember(day) { mutableStateOf(stored) }
    var dirty by remember(day) { mutableStateOf(false) }
    LaunchedEffect(stored) { if (!dirty) text = stored }
    LaunchedEffect(text, dirty) {
        if (dirty) {
            delay(800)
            repo.saveJournal(day, text)
            dirty = false
        }
    }
    DisposableEffect(day) {
        onDispose { if (dirty) repo.saveJournal(day, text) }
    }
    OutlinedTextField(text, { text = it; dirty = true }, Modifier.fillMaxWidth().heightIn(min = 120.dp),
        placeholder = { Text(stringResource(R.string.day_note_hint)) })
}
