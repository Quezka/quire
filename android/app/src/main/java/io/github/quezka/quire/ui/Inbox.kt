package io.github.quezka.quire.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.Ideas
import java.text.DateFormat
import java.time.LocalDate
import java.util.Date

private const val SHOWN = 4

/** Today's inbox (replaced day notes, 0.52): notifications Quire held + ideas waiting for a decision. */
@Composable
fun InboxCard(container: Container, version: Int, day: LocalDate) {
    var local by remember { mutableIntStateOf(0) }
    val hub = container.hub
    val repo = container.repository
    val held = remember(version, local) { hub.held() }
    val ideas = remember(version, local) { repo.ideas().filter { !it.done }.sortedByDescending { it.created } }
    var showHeld by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (held.isEmpty() && ideas.isEmpty()) Hint(stringResource(R.string.inbox_empty))
            if (held.isNotEmpty()) Row(Modifier.fillMaxWidth().clickable { showHeld = true },
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.inbox_held, held.size), style = MaterialTheme.typography.titleMedium)
                    Text(held.takeLast(3).reversed().joinToString(" · ") { appName(container, it.app) },
                        maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
                }
                TextButton({ showHeld = true }) { Text(stringResource(R.string.inbox_open_held)) }
            }
            for (idea in ideas.take(SHOWN)) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(Ideas.firstLine(idea.text), Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                TextButton({ repo.ideaToTask(idea.uid, day); local++ }) { Text(stringResource(R.string.inbox_to_task)) }
                TextButton({ repo.setIdeaDone(idea.uid, true); local++ }) { Text(stringResource(R.string.inbox_done)) }
            }
            if (ideas.size > SHOWN) Hint(stringResource(R.string.inbox_more_ideas, ideas.size - SHOWN))
        }
    }
    if (showHeld) HeldDialog(container, onClose = { showHeld = false; local++ })
}

/** Old versions saved package ids as names: show the app's name instead. */
private fun appName(container: Container, app: String): String =
    if (app.contains('.') && !app.contains(' ')) container.hub.label(app) else app

@Composable
fun HeldDialog(container: Container, onClose: () -> Unit) {
    val hub = container.hub
    val held = remember { hub.held().reversed() }
    val time = remember { DateFormat.getTimeInstance(DateFormat.SHORT) }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.held_title)) },
        text = {
            if (held.isEmpty()) Text(stringResource(R.string.held_empty))
            else LazyColumn(Modifier.heightIn(max = 480.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(held) { h ->
                    Column {
                        Text("${appName(container, h.app)} · ${time.format(Date(h.at))}",
                            style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                        if (h.title.isNotBlank()) Text(h.title, style = MaterialTheme.typography.titleSmall)
                        if (h.text.isNotBlank()) Text(h.text, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        },
        confirmButton = { TextButton(onClose) { Text(stringResource(android.R.string.ok)) } },
        dismissButton = if (held.isEmpty()) null else ({ TextButton({ hub.clearHeld(); onClose() }) { Text(stringResource(R.string.held_clear)) } }),
    )
}
