package io.github.quezka.quire.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PushPin
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Note
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotesScreen(repo: Repository, version: Int, openNote: (String) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    val context = androidx.compose.ui.platform.LocalContext.current
    val notes = remember(version) { repo.notes() }
    val courses = remember(version) { repo.courses().associateBy { it.uid } }
    val shown = notes.filter {
        query.isBlank() || it.body.contains(query, ignoreCase = true) || it.topic.contains(query, true)
    }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            TopAppBar(title = { Text(stringResource(R.string.nav_notes)) })
            OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                placeholder = { Text(stringResource(R.string.search_notes)) }, singleLine = true,
                leadingIcon = { Icon(Icons.Filled.Search, null) })
            if (shown.isEmpty()) Box(Modifier.padding(16.dp)) { Hint(stringResource(R.string.no_notes)) }
            LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp)) {
                items(shown, key = { it.uid }) { note ->
                    Row(Modifier.fillMaxWidth().clickable { openNote(note.uid) }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        courses[note.courseUid]?.let {
                            Box(Modifier.size(10.dp).padding(0.dp)) {
                                androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
                                    drawCircle(parseColor(it.color))
                                }
                            }
                            Spacer(Modifier.width(10.dp))
                        }
                        Column(Modifier.weight(1f)) {
                            Text(note.title, fontWeight = FontWeight.SemiBold, maxLines = 1,
                                overflow = TextOverflow.Ellipsis)
                            val updated = runCatching { java.time.LocalDate.parse(note.updated.take(10)) }
                                .getOrNull()?.let { relativeDate(context, it, repo.today()) }
                            val meta = listOfNotNull(courses[note.courseUid]?.name,
                                note.topic.ifBlank { null }, updated)
                            Text(meta.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                        }
                        if (note.pinned) Icon(Icons.Filled.PushPin, stringResource(R.string.pinned),
                            tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
        }
        FloatingActionButton(onClick = {
            val note = repo.saveNote(Note(Codec.newUid(), ""))
            openNote(note.uid)
        }, modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            Icon(Icons.Filled.Add, stringResource(R.string.new_note))
        }
    }
}

/** Full-screen editor; saves shortly after typing stops and when leaving. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteEditor(repo: Repository, version: Int, uid: String, close: () -> Unit) {
    val stored = remember(version) { repo.note(uid) }
    var body by remember { mutableStateOf(stored?.body.orEmpty()) }
    var topic by remember { mutableStateOf(stored?.topic.orEmpty()) }
    var courseUid by remember { mutableStateOf(stored?.courseUid) }
    var pinned by remember { mutableStateOf(stored?.pinned ?: false) }
    var dirty by remember { mutableStateOf(false) }
    var confirming by remember { mutableStateOf(false) }
    val courses = remember(version) { repo.courses() }

    fun flush() {
        if (!dirty) return
        val base = repo.note(uid) ?: Note(uid, "")
        repo.saveNote(base.copy(body = body, topic = topic, courseUid = courseUid, pinned = pinned))
        dirty = false
    }

    // A sync brought a newer version: show it, unless there are unsaved edits (they win).
    LaunchedEffect(stored) {
        if (!dirty && stored != null) {
            body = stored.body; topic = stored.topic; courseUid = stored.courseUid; pinned = stored.pinned
        }
    }
    LaunchedEffect(body, topic, courseUid, pinned, dirty) { if (dirty) { delay(800); flush() } }
    DisposableEffect(uid) { onDispose { flush() } }
    BackHandler { flush(); close() }

    Column(Modifier.fillMaxSize().imePadding()) {
        TopAppBar(
            title = { Text(io.github.quezka.quire.domain.deriveNoteTitle(body), maxLines = 1,
                overflow = TextOverflow.Ellipsis) },
            navigationIcon = {
                IconButton(onClick = { flush(); close() }) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back))
                }
            },
            actions = {
                IconButton(onClick = { pinned = !pinned; dirty = true }) {
                    Icon(if (pinned) Icons.Filled.PushPin else Icons.Outlined.PushPin,
                        stringResource(if (pinned) R.string.unpin else R.string.pin))
                }
                IconButton(onClick = { confirming = true }) {
                    Icon(Icons.Filled.Delete, stringResource(R.string.delete))
                }
            },
        )
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f)) { CoursePicker(courses, courseUid) { courseUid = it; dirty = true } }
            OutlinedTextField(topic, { topic = it; dirty = true }, Modifier.weight(1f),
                label = { Text(stringResource(R.string.topic)) }, singleLine = true)
        }
        TextField(body, { body = it; dirty = true }, Modifier.fillMaxSize().padding(top = 8.dp),
            placeholder = { Text(stringResource(R.string.note_hint)) },
            colors = TextFieldDefaults.colors(
                focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
                focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent))
    }

    if (confirming) ConfirmDialog(stringResource(R.string.delete_note_question),
        stringResource(R.string.delete),
        onConfirm = { dirty = false; repo.deleteNote(uid); confirming = false; close() },
        onDismiss = { confirming = false })
}
