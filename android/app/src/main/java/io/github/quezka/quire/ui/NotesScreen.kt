package io.github.quezka.quire.ui

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.FormatIndentDecrease
import androidx.compose.material.icons.automirrored.filled.FormatIndentIncrease
import androidx.compose.material.icons.automirrored.filled.FormatListBulleted
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.ChecklistRtl
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DocumentScanner
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.FormatBold
import androidx.compose.material.icons.filled.FormatItalic
import androidx.compose.material.icons.filled.FormatQuote
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PushPin
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Title
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.BlockKind
import io.github.quezka.quire.domain.Markdown
import io.github.quezka.quire.domain.COURSE_COLORS
import io.github.quezka.quire.domain.Note
import io.github.quezka.quire.domain.Notebook
import io.github.quezka.quire.domain.deriveNoteTitle
import io.github.quezka.quire.ocr.Ocr
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.LocalDate

/** Which notes show: everything, pinned ones, or one course's. */
private const val ALL = "*"
private const val PINNED = "pinned"
private const val NOTEBOOK = "nb:" // "nb:<uid>" filters to one notebook; a bare uid is a course

private fun homed(filter: String) = filter != ALL && filter != PINNED

/** (course uid, notebook uid) a new note gets when the list is filtered to [filter]. */
private fun filterHome(filter: String): Pair<String?, String?> = when {
    !homed(filter) -> null to null
    filter.startsWith(NOTEBOOK) -> null to filter.removePrefix(NOTEBOOK)
    else -> filter to null
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun NotesScreen(repo: Repository, version: Int, openNote: (String) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    var searching by rememberSaveable { mutableStateOf(false) }
    var filter by rememberSaveable { mutableStateOf(ALL) }
    var topic by rememberSaveable { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val notes = remember(version) { repo.notes() }
    val courses = remember(version) { repo.courses() }
    val courseIndex = remember(version) { repo.courseIndex() }
    val notebooks = remember(version) { repo.notebooks() }
    val notebookIndex = remember(version) { notebooks.associateBy { it.uid } }
    var notebookDialog by remember { mutableStateOf<Notebook?>(null) }
    var newNotebook by remember { mutableStateOf(false) }
    var deletingNotebook by remember { mutableStateOf<Notebook?>(null) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var menu by remember { mutableStateOf(false) }
    val scanner = rememberScanner { text ->
        val (course, notebook) = filterHome(filter)
        val note = repo.saveNote(Note(Codec.newUid(),
            context.getString(R.string.scanned_title, longDate(repo.today(), repo.today())) + "\n\n" + text,
            courseUid = course, notebookUid = notebook, topic = topic.orEmpty()))
        openNote(note.uid)
    }

    val inFilter = notes.filter { n ->
        when (filter) {
            ALL -> true
            PINNED -> n.pinned
            else -> if (filter.startsWith(NOTEBOOK)) n.notebookUid == filter.removePrefix(NOTEBOOK)
                else courseIndex[n.courseUid]?.uid == filter
        }
    }
    val topics = if (homed(filter))
        inFilter.map { it.topic }.filter { it.isNotBlank() }.distinct().sortedBy { it.lowercase() } else emptyList()
    val shown = inFilter.filter { n ->
        (topic == null || n.topic == topic) &&
            (query.isBlank() || n.body.contains(query, ignoreCase = true) || n.topic.contains(query, true))
    }
    // With a course or notebook chosen, notes are grouped under their topics.
    val grouped = if (homed(filter) && topic == null && topics.isNotEmpty())
        shown.groupBy { it.topic }.toSortedMap(compareBy({ it.isEmpty() }, { it.lowercase() }))
    else mapOf("" to shown)

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            TopAppBar(title = {
                AnimatedContent(searching, label = "search") { on ->
                    if (!on) Text(stringResource(R.string.nav_notes))
                    else OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth().padding(end = 8.dp),
                        placeholder = { Text(stringResource(R.string.search_notes)) }, singleLine = true,
                        leadingIcon = { Icon(Icons.Filled.Search, null) })
                }
            }, actions = {
                IconButton(onClick = { searching = !searching; if (!searching) query = "" }) {
                    Icon(if (searching) Icons.Filled.Close else Icons.Filled.Search, stringResource(R.string.search_notes))
                }
            })
            // Course and notebook chips, then (for one of them) its topics.
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(filter == ALL, { filter = ALL; topic = null }, { Text(stringResource(R.string.all_notes)) })
                if (notes.any { it.pinned }) FilterChip(filter == PINNED, { filter = PINNED; topic = null },
                    { Text(stringResource(R.string.pinned)) }, leadingIcon = { Icon(Icons.Filled.PushPin, null, Modifier.size(16.dp)) })
                for (c in courses.filter { c -> notes.any { courseIndex[it.courseUid]?.uid == c.uid } }) {
                    FilterChip(filter == c.uid, { filter = if (filter == c.uid) ALL else c.uid; topic = null },
                        { Text(c.name) }, leadingIcon = {
                            Box(Modifier.size(10.dp).background(parseColor(c.color), CircleShape))
                        })
                }
                for (b in notebooks) {
                    val key = NOTEBOOK + b.uid
                    FilterChip(filter == key, { filter = if (filter == key) ALL else key; topic = null },
                        { Text(b.name) }, leadingIcon = {
                            Box(Modifier.size(10.dp).background(parseColor(b.color), CircleShape))
                        })
                }
                notebookIndex[filter.removePrefix(NOTEBOOK)]?.takeIf { filter.startsWith(NOTEBOOK) }?.let { open ->
                    IconButton(onClick = { notebookDialog = open }, Modifier.size(32.dp)) {
                        Icon(Icons.Filled.Edit, stringResource(R.string.edit_notebook), Modifier.size(18.dp))
                    }
                }
                AssistChip({ newNotebook = true }, { Text(stringResource(R.string.new_notebook)) },
                    leadingIcon = { Icon(Icons.Filled.Add, null, Modifier.size(16.dp)) })
            }
            AnimatedVisibility(topics.isNotEmpty(), enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (t in topics) FilterChip(topic == t, { topic = if (topic == t) null else t }, { Text(t) })
                }
            }
            if (shown.isEmpty()) Box(Modifier.padding(16.dp)) {
                Hint(stringResource(if (notes.isEmpty()) R.string.no_notes else R.string.no_matching_notes))
            }
            LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((groupTopic, list) in grouped) {
                    if (grouped.size > 1) item(key = "topic-$groupTopic") {
                        Text(groupTopic.ifEmpty { stringResource(R.string.no_topic) },
                            style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.animateItem().padding(top = 8.dp))
                    }
                    items(list, key = { it.uid }) { note ->
                        val dismiss = rememberSwipeToDismissBoxState(confirmValueChange = { value ->
                            if (value == SwipeToDismissBoxValue.Settled) return@rememberSwipeToDismissBoxState false
                            val kept = note
                            repo.deleteNote(note.uid)
                            scope.launch {
                                val result = snackbar.showSnackbar(context.getString(R.string.note_deleted),
                                    context.getString(R.string.undo), duration = SnackbarDuration.Short)
                                if (result == SnackbarResult.ActionPerformed) repo.saveNote(kept)
                            }
                            true
                        })
                        SwipeToDismissBox(dismiss, modifier = Modifier.animateItem(), backgroundContent = {
                            val active = dismiss.targetValue != SwipeToDismissBoxValue.Settled
                            val bg by animateColorAsState(if (active) MaterialTheme.colorScheme.errorContainer else Color.Transparent,
                                label = "swipe")
                            Box(Modifier.fillMaxSize().background(bg, RoundedCornerShape(16.dp)).padding(horizontal = 24.dp),
                                contentAlignment = if (dismiss.dismissDirection == SwipeToDismissBoxValue.StartToEnd)
                                    Alignment.CenterStart else Alignment.CenterEnd) {
                                Icon(Icons.Filled.Delete, stringResource(R.string.delete),
                                    tint = MaterialTheme.colorScheme.onErrorContainer)
                            }
                        }) {
                            NoteCard(note, courseIndex[note.courseUid], notebookIndex[note.notebookUid],
                                repo.today(), showCourse = !homed(filter),
                                onOpen = { openNote(note.uid) },
                                onPin = { repo.saveNote(note.copy(pinned = !note.pinned)) })
                        }
                    }
                }
            }
        }
        Column(Modifier.align(Alignment.BottomEnd).padding(20.dp), horizontalAlignment = Alignment.End) {
            FloatingActionButton(onClick = { menu = true }) {
                val turn by animateFloatAsState(if (menu) 45f else 0f, Motion.bouncy(), label = "fab")
                Icon(Icons.Filled.Add, stringResource(R.string.new_note), Modifier.graphicsLayer { rotationZ = turn })
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem(text = { Text(stringResource(R.string.new_note)) },
                        leadingIcon = { Icon(Icons.Filled.Edit, null) }, onClick = {
                            menu = false
                            val (course, notebook) = filterHome(filter)
                            openNote(repo.saveNote(Note(Codec.newUid(), "", courseUid = course,
                                notebookUid = notebook, topic = topic.orEmpty())).uid)
                        })
                    DropdownMenuItem(text = { Text(stringResource(R.string.new_notebook)) },
                        leadingIcon = { Icon(Icons.Filled.Book, null) }, onClick = { menu = false; newNotebook = true })
                    DropdownMenuItem(text = { Text(stringResource(R.string.scan_page)) },
                        leadingIcon = { Icon(Icons.Filled.CameraAlt, null) }, onClick = { menu = false; scanner.camera() })
                    DropdownMenuItem(text = { Text(stringResource(R.string.from_picture)) },
                        leadingIcon = { Icon(Icons.Filled.Image, null) }, onClick = { menu = false; scanner.gallery() })
                }
            }
        }
        SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 88.dp))
        ScanProgress(scanner.busy)
    }

    if (newNotebook) NotebookDialog(null, onDismiss = { newNotebook = false }, onDelete = null,
        onSave = { saved ->
            newNotebook = false
            filter = NOTEBOOK + repo.saveNotebook(saved).uid; topic = null
        })
    notebookDialog?.let { open ->
        NotebookDialog(open, onDismiss = { notebookDialog = null },
            onDelete = { deletingNotebook = open; notebookDialog = null },
            onSave = { repo.saveNotebook(it); notebookDialog = null })
    }
    deletingNotebook?.let { doomed ->
        ConfirmDialog(stringResource(R.string.delete_notebook_question, doomed.name),
            stringResource(R.string.delete),
            onConfirm = {
                repo.deleteNotebook(doomed.uid)
                if (filter == NOTEBOOK + doomed.uid) { filter = ALL; topic = null }
                deletingNotebook = null
            },
            onDismiss = { deletingNotebook = null })
    }
}

/** Name and colour of a notebook: new (`initial` is null), or rename, recolour and delete. */
@Composable
fun NotebookDialog(initial: Notebook?, onSave: (Notebook) -> Unit, onDelete: (() -> Unit)?,
                   onDismiss: () -> Unit) {
    var name by remember { mutableStateOf(initial?.name.orEmpty()) }
    var color by remember { mutableStateOf(initial?.color ?: COURSE_COLORS[4]) }
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(if (initial == null) R.string.new_notebook else R.string.edit_notebook)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text(stringResource(R.string.notebook_name)) },
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences))
                ColorPicker(color) { color = it }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank(), onClick = {
                onSave(Notebook(initial?.uid ?: Codec.newUid(), name.trim(), color))
            }) { Text(stringResource(R.string.save)) }
        },
        dismissButton = {
            Row {
                if (onDelete != null) TextButton(onClick = onDelete,
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)) {
                    Text(stringResource(R.string.delete))
                }
                TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
            }
        })
}

/** Where a note is filed: no group, a course, or a notebook (or make a new notebook). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HomePicker(courses: List<io.github.quezka.quire.domain.Course>, notebooks: List<Notebook>,
                       courseUid: String?, notebookUid: String?, onNew: () -> Unit,
                       onPick: (course: String?, notebook: String?) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val name = courses.firstOrNull { it.uid == courseUid }?.name
        ?: notebooks.firstOrNull { it.uid == notebookUid }?.name
        ?: stringResource(R.string.no_course_or_notebook)
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(name, {}, readOnly = true, singleLine = true,
            label = { Text(stringResource(R.string.course_or_notebook)) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor())
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            DropdownMenuItem(text = { Text(stringResource(R.string.no_course_or_notebook)) },
                onClick = { onPick(null, null); open = false })
            for (c in courses) DropdownMenuItem(text = { Text(c.name) },
                leadingIcon = { Box(Modifier.size(10.dp).background(parseColor(c.color), CircleShape)) },
                onClick = { onPick(c.uid, null); open = false })
            if (notebooks.isNotEmpty()) HorizontalDivider()
            for (b in notebooks) DropdownMenuItem(text = { Text(b.name) },
                leadingIcon = { Box(Modifier.size(10.dp).background(parseColor(b.color), CircleShape)) },
                onClick = { onPick(null, b.uid); open = false })
            HorizontalDivider()
            DropdownMenuItem(text = { Text(stringResource(R.string.new_notebook)) },
                leadingIcon = { Icon(Icons.Filled.Add, null) },
                onClick = { open = false; onNew() })
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun NoteCard(note: Note, course: io.github.quezka.quire.domain.Course?, notebook: Notebook?,
                     today: LocalDate, showCourse: Boolean, onOpen: () -> Unit, onPin: () -> Unit) {
    val context = LocalContext.current
    val source = remember { MutableInteractionSource() }
    val snippet = remember(note.body) { Markdown.snippet(note.body, 140) }
    Card(Modifier.fillMaxWidth().pressScale(source)
        .combinedClickable(source, null, onClick = onOpen, onLongClick = onPin),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
            Box(Modifier.width(5.dp).fillMaxHeight()
                .background((course?.color ?: notebook?.color)?.let { parseColor(it) } ?: Color.Transparent))
            Column(Modifier.weight(1f).padding(14.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(note.title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    AnimatedVisibility(note.pinned) {
                        Icon(Icons.Filled.PushPin, stringResource(R.string.pinned),
                            tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                    }
                }
                if (snippet.isNotEmpty()) Text(snippet, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                val updated = runCatching { LocalDate.parse(note.updated.take(10)) }.getOrNull()
                    ?.let { relativeDate(context, it, today) }
                val meta = listOfNotNull((course?.name ?: notebook?.name)?.takeIf { showCourse }, note.topic.ifBlank { null }, updated)
                if (meta.isNotEmpty()) Text(meta.joinToString(" · "), style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f), maxLines = 1)
            }
        }
    }
}

// ---- scanning printed pages ----

class Scanner(val camera: () -> Unit, val gallery: () -> Unit, val busy: Boolean)

/** Photograph a page (or pick a picture) and read its text; [onText] gets the tidied text. */
@Composable
fun rememberScanner(onText: (String) -> Unit): Scanner {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var photo by rememberSaveable { mutableStateOf<String?>(null) }

    fun read(uri: Uri) {
        busy = true
        scope.launch {
            val result = runCatching { withContext(Dispatchers.Default) { Ocr(context).read(uri) } }
            busy = false
            result.onSuccess { text ->
                if (text.isBlank()) error = context.getString(R.string.no_text_found) else onText(text)
            }.onFailure { error = context.getString(R.string.no_text_found) }
        }
    }
    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) photo?.let { read(Uri.parse(it)) }
    }
    fun shoot() {
        val dir = File(context.cacheDir, "scans").apply { mkdirs() }
        val file = File(dir, "page-${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        photo = uri.toString()
        takePicture.launch(uri)
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) shoot()
    }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let(::read) }
    error?.let { message ->
        androidx.compose.material3.AlertDialog(onDismissRequest = { error = null }, text = { Text(message) },
            confirmButton = { androidx.compose.material3.TextButton(onClick = { error = null }) { Text(stringResource(R.string.ok)) } })
    }
    return Scanner(
        camera = {
            // The app declares the camera (for QR codes), so Android wants the permission
            // even though the photo is taken by the camera app.
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) shoot()
            else permission.launch(Manifest.permission.CAMERA)
        },
        gallery = { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
        busy = busy,
    )
}

@Composable
private fun ScanProgress(busy: Boolean) {
    AnimatedVisibility(busy, enter = fadeIn(), exit = fadeOut()) {
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.35f)), contentAlignment = Alignment.Center) {
            Card(shape = RoundedCornerShape(20.dp)) {
                Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Filled.DocumentScanner, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.primary)
                    Text(stringResource(R.string.reading_page))
                    LinearProgressIndicator(Modifier.width(180.dp))
                }
            }
        }
    }
}

// ---- the editor ----

/** Full-screen editor: you write into the formatted note. Saves shortly after typing
 *  stops and when leaving. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteEditor(repo: Repository, version: Int, uid: String, close: () -> Unit) {
    val stored = remember(version) { repo.note(uid) }
    var dirty by remember { mutableStateOf(false) }
    val editor = remember(uid) { BlockEditorState(stored?.body.orEmpty()) { dirty = true } }
    var topic by remember { mutableStateOf(stored?.topic.orEmpty()) }
    var courseUid by remember { mutableStateOf(stored?.courseUid) }
    var notebookUid by remember { mutableStateOf(stored?.notebookUid) }
    var newNotebook by remember { mutableStateOf(false) }
    var pinned by remember { mutableStateOf(stored?.pinned ?: false) }
    var confirming by remember { mutableStateOf(false) }
    var overflow by remember { mutableStateOf(false) }
    val courses = remember(version) { repo.courses() }
    val notebooks = remember(version) { repo.notebooks() }
    val topics = remember(version, courseUid, notebookUid) {
        repo.notes().filter { it.courseUid == courseUid && it.notebookUid == notebookUid && it.topic.isNotBlank() }
            .map { it.topic }.distinct().sorted()
    }
    val body = remember(editor.revision) { editor.markdown() }

    fun flush() {
        if (!dirty) return
        val base = repo.note(uid) ?: Note(uid, "")
        repo.saveNote(base.copy(body = editor.markdown(), topic = topic, courseUid = courseUid,
            notebookUid = notebookUid, pinned = pinned))
        dirty = false
    }
    // A scanned page's text goes where the cursor is.
    val scanner = rememberScanner { text -> editor.insertText(text) }

    // A sync brought a newer version: show it, unless there are unsaved edits (they win).
    LaunchedEffect(stored) {
        if (!dirty && stored != null && stored.body != editor.markdown()) {
            editor.load(stored.body)
            topic = stored.topic; courseUid = stored.courseUid; notebookUid = stored.notebookUid
            pinned = stored.pinned
        }
    }
    LaunchedEffect(editor.revision, topic, courseUid, notebookUid, pinned, dirty) { if (dirty) { delay(800); flush() } }
    DisposableEffect(uid) { onDispose { flush() } }
    BackHandler { flush(); close() }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().imePadding()) {
            TopAppBar(
                title = { Text(deriveNoteTitle(body), maxLines = 1, overflow = TextOverflow.Ellipsis) },
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
                    IconButton(onClick = { overflow = true }) {
                        Icon(Icons.Filled.MoreVert, null)
                        DropdownMenu(overflow, { overflow = false }) {
                            DropdownMenuItem(text = { Text(stringResource(R.string.scan_page)) },
                                leadingIcon = { Icon(Icons.Filled.CameraAlt, null) },
                                onClick = { overflow = false; scanner.camera() })
                            DropdownMenuItem(text = { Text(stringResource(R.string.from_picture)) },
                                leadingIcon = { Icon(Icons.Filled.Image, null) },
                                onClick = { overflow = false; scanner.gallery() })
                            DropdownMenuItem(text = { Text(stringResource(R.string.delete)) },
                                leadingIcon = { Icon(Icons.Filled.Delete, null) },
                                onClick = { overflow = false; confirming = true })
                        }
                    }
                },
            )
            Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.weight(1f)) {
                    HomePicker(courses, notebooks, courseUid, notebookUid, onNew = { newNotebook = true }) { course, book ->
                        courseUid = course; notebookUid = book; dirty = true
                    }
                }
                TopicField(topic, topics, Modifier.weight(1f)) { topic = it; dirty = true }
            }
            BlockEditor(editor, repo::image, stringResource(R.string.note_hint),
                Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp, vertical = 12.dp))
            FormatBar(editor)
        }
        ScanProgress(scanner.busy)
    }

    if (newNotebook) NotebookDialog(null, onDismiss = { newNotebook = false }, onDelete = null,
        onSave = { saved ->
            newNotebook = false
            courseUid = null; notebookUid = repo.saveNotebook(saved).uid; dirty = true
        })

    if (confirming) ConfirmDialog(stringResource(R.string.delete_note_question),
        stringResource(R.string.delete),
        onConfirm = { dirty = false; repo.deleteNote(uid); confirming = false; close() },
        onDismiss = { confirming = false })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TopicField(topic: String, suggestions: List<String>, modifier: Modifier, onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val matching = suggestions.filter { it != topic && it.contains(topic, ignoreCase = true) }
    androidx.compose.material3.ExposedDropdownMenuBox(open && matching.isNotEmpty(), { open = it }, modifier) {
        OutlinedTextField(topic, { onChange(it); open = true }, Modifier.menuAnchor(), singleLine = true,
            label = { Text(stringResource(R.string.topic)) })
        ExposedDropdownMenu(open && matching.isNotEmpty(), { open = false }) {
            for (s in matching) DropdownMenuItem(text = { Text(s) }, onClick = { onChange(s); open = false })
        }
    }
}

/** Formatting buttons above the keyboard; they act on the line being edited. */
@Composable
private fun FormatBar(editor: BlockEditorState) {
    val context = LocalContext.current
    Column {
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceContainer)
            .horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            FormatButton(Icons.Filled.Title, R.string.heading) { editor.setKind(BlockKind.HEADING, 2) }
            FormatButton(Icons.Filled.FormatBold, R.string.bold) { editor.wrap("**", context.getString(R.string.bold_placeholder)) }
            FormatButton(Icons.Filled.FormatItalic, R.string.italic) { editor.wrap("*", context.getString(R.string.italic_placeholder)) }
            FormatButton(Icons.AutoMirrored.Filled.FormatListBulleted, R.string.bulleted_list) { editor.setKind(BlockKind.BULLET) }
            FormatButton(Icons.Filled.ChecklistRtl, R.string.checklist) { editor.setKind(BlockKind.CHECK) }
            FormatButton(Icons.AutoMirrored.Filled.FormatIndentIncrease, R.string.indent) { editor.indent(true) }
            FormatButton(Icons.AutoMirrored.Filled.FormatIndentDecrease, R.string.outdent) { editor.indent(false) }
            FormatButton(Icons.Filled.FormatQuote, R.string.quote) { editor.setKind(BlockKind.QUOTE, 1) }
            FormatButton(Icons.Filled.Code, R.string.code) { editor.wrap("`", context.getString(R.string.code_placeholder)) }
            Spacer(Modifier.width(12.dp))
            val words = editor.words
            if (words > 0) Text(pluralStringResource(R.plurals.words, words, words),
                style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(end = 12.dp))
        }
    }
}

@Composable
private fun FormatButton(icon: ImageVector, label: Int, onClick: () -> Unit) {
    IconButton(onClick = onClick) { Icon(icon, stringResource(label)) }
}
