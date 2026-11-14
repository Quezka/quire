package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R

/** Ideas: type one and press Enter; tick it when it's dealt with. New ones come back in the evening digest. */
@Composable
fun IdeasScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val ideas = remember(version) { repo.ideas() }
    var text by rememberSaveable { mutableStateOf("") }
    fun add() { if (repo.addIdea(text) != null) text = "" }
    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_ideas), back)
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(text, { text = it }, Modifier.weight(1f), label = { Text(stringResource(R.string.idea_jot)) },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), keyboardActions = KeyboardActions(onDone = { add() }))
            Button(onClick = ::add, enabled = text.isNotBlank()) { Text(stringResource(R.string.add)) }
        }
        Text(stringResource(R.string.ideas_hint), Modifier.padding(16.dp, 8.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        if (ideas.isEmpty()) Text(stringResource(R.string.ideas_none), Modifier.padding(16.dp))
        LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 96.dp)) {
            items(ideas, key = { it.uid }) { idea ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(idea.done, { repo.setIdeaDone(idea.uid, it) })
                    Text(idea.text, Modifier.weight(1f).padding(vertical = 12.dp),
                        textDecoration = if (idea.done) TextDecoration.LineThrough else null,
                        color = if (idea.done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
                    IconButton(onClick = { repo.deleteIdea(idea.uid) }) {
                        Icon(Icons.Filled.Delete, stringResource(R.string.delete))
                    }
                }
            }
        }
    }
}
