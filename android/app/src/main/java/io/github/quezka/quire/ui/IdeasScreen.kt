package io.github.quezka.quire.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.Idea
import io.github.quezka.quire.domain.Ideas
import kotlinx.coroutines.launch

/** Ideas: type one and press Enter; find it again (search, #tags); act on it (task, note, done). Deleting has Undo. */
@Composable
fun IdeasScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val context = LocalContext.current
    val all = remember(version) { repo.ideas() }
    var query by rememberSaveable { mutableStateOf("") }
    val ideas = remember(all, query) { all.filter { Ideas.matches(it, query) } }
    val tags = remember(all) { Ideas.allTags(all).take(8) }
    var text by rememberSaveable { mutableStateOf("") }
    var editing by remember { mutableStateOf<Idea?>(null) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    fun say(message: String, undo: (() -> Unit)? = null) = scope.launch {
        snackbar.currentSnackbarData?.dismiss()
        val result = snackbar.showSnackbar(message, actionLabel = undo?.let { context.getString(R.string.undo) },
            withDismissAction = undo == null)
        if (result == SnackbarResult.ActionPerformed) undo?.invoke()
    }
    fun add() { if (repo.addIdea(text) != null) { text = ""; say(context.getString(R.string.idea_caught)) } }
    fun toggleTag(tag: String) {
        val words = query.split(Regex("\\s+")).filter { it.isNotEmpty() && it != "#$tag" }
        query = (if ("#$tag" in query.split(Regex("\\s+"))) words else words + "#$tag").joinToString(" ")
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbar) }, containerColor = MaterialTheme.colorScheme.background) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).imePadding()) {
            PageBar(stringResource(R.string.nav_ideas), back) {
                var exportMenu by remember { mutableStateOf(false) }
                IconButton(onClick = { exportMenu = true }) { Icon(Icons.Filled.Share, stringResource(R.string.ideas_export)) }
                androidx.compose.material3.DropdownMenu(exportMenu, { exportMenu = false }) {
                    androidx.compose.material3.DropdownMenuItem({ Text(stringResource(R.string.ideas_share)) }, onClick = {
                        exportMenu = false
                        val text = Ideas.exportText(ideas.filter { !it.done })
                        if (text.isBlank()) say(context.getString(R.string.ideas_none_to_export))
                        else context.startActivity(android.content.Intent.createChooser(
                            android.content.Intent(android.content.Intent.ACTION_SEND).setType("text/plain")
                                .putExtra(android.content.Intent.EXTRA_TEXT, text), null))
                    })
                    androidx.compose.material3.DropdownMenuItem({ Text(stringResource(R.string.ideas_one_note)) }, onClick = {
                        exportMenu = false
                        val text = Ideas.exportText(ideas.filter { !it.done })
                        if (text.isBlank()) say(context.getString(R.string.ideas_none_to_export))
                        else {
                            repo.saveNote(io.github.quezka.quire.domain.Note(io.github.quezka.quire.data.Codec.newUid(),
                                "# " + context.getString(R.string.nav_ideas) + "\n\n" + text))
                            say(context.getString(R.string.ideas_in_one_note))
                        }
                    })
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(text, { text = it }, Modifier.weight(1f), label = { Text(stringResource(R.string.idea_jot_tags)) },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), keyboardActions = KeyboardActions(onDone = { add() }))
                Button(onClick = ::add, enabled = text.isNotBlank()) { Text(stringResource(R.string.add)) }
            }
            if (all.size > 3) {
                OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth().padding(16.dp, 8.dp, 16.dp, 0.dp),
                    leadingIcon = { Icon(Icons.Filled.Search, null) }, singleLine = true,
                    placeholder = { Text(stringResource(R.string.ideas_search)) })
            }
            if (tags.isNotEmpty()) {
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (tag in tags) FilterChip("#$tag" in query.split(Regex("\\s+")), { toggleTag(tag) }, { Text("#$tag") })
                }
            }
            if (all.isEmpty()) Text(stringResource(R.string.ideas_hint), Modifier.padding(16.dp, 8.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
            if (ideas.isEmpty()) Text(stringResource(if (query.isBlank()) R.string.ideas_none else R.string.ideas_no_match),
                Modifier.padding(16.dp))
            LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 96.dp)) {
                items(ideas, key = { it.uid }) { idea ->
                    var menu by remember { mutableStateOf(false) }
                    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(idea.done, { repo.setIdeaDone(idea.uid, it) })
                        Text(idea.text, Modifier.weight(1f).clickable { editing = idea }.padding(vertical = 12.dp),
                            textDecoration = if (idea.done) TextDecoration.LineThrough else null,
                            style = MaterialTheme.typography.bodyLarge,
                            color = if (idea.done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
                        Box {
                            IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, stringResource(R.string.nav_more)) }
                            DropdownMenu(menu, { menu = false }) {
                                DropdownMenuItem({ Text(stringResource(R.string.idea_to_task_today)) }, {
                                    menu = false; repo.ideaToTask(idea.uid, java.time.LocalDate.now())
                                    say(context.getString(R.string.idea_now_task_today))
                                })
                                DropdownMenuItem({ Text(stringResource(R.string.idea_to_task)) }, {
                                    menu = false; repo.ideaToTask(idea.uid, null); say(context.getString(R.string.idea_now_task))
                                })
                                DropdownMenuItem({ Text(stringResource(R.string.idea_to_note)) }, {
                                    menu = false; repo.ideaToNote(idea.uid); say(context.getString(R.string.idea_now_note))
                                })
                                DropdownMenuItem({ Text(stringResource(R.string.delete)) }, {
                                    menu = false; repo.deleteIdea(idea.uid)
                                    say(context.getString(R.string.idea_deleted)) { repo.restoreIdea(idea) }
                                })
                            }
                        }
                    }
                }
            }
        }
    }
    editing?.let { idea ->
        var draft by remember(idea.uid) { mutableStateOf(idea.text) }
        AlertDialog(onDismissRequest = { editing = null },
            title = { Text(stringResource(R.string.idea_edit)) },
            text = { OutlinedTextField(draft, { draft = it }, Modifier.fillMaxWidth(), minLines = 3) },
            confirmButton = { TextButton(onClick = { repo.editIdea(idea.uid, draft); editing = null }) { Text(stringResource(R.string.save)) } },
            dismissButton = { TextButton(onClick = { editing = null }) { Text(stringResource(R.string.cancel)) } })
    }
}
