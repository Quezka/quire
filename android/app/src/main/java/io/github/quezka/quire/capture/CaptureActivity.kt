package io.github.quezka.quire.capture

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.container
import io.github.quezka.quire.ui.QuireTheme

/** Catch an idea in a second, from anywhere: the widget, the quick-settings tile, the app-icon shortcut, or text
 *  shared from another app. A small card over whatever was on screen, keyboard up, Enter saves and closes. */
class CaptureActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val shared = if (intent?.action == Intent.ACTION_SEND) intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty() else ""
        setContent {
            QuireTheme {
                var text by remember { mutableStateOf(shared) }
                val focus = remember { FocusRequester() }
                LaunchedEffect(Unit) { focus.requestFocus() }
                fun save() {
                    if (container.repository.addIdea(text) != null) {
                        android.widget.Toast.makeText(this, R.string.idea_caught, android.widget.Toast.LENGTH_SHORT).show()
                        finish()
                    }
                }
                Surface(Modifier.fillMaxWidth().padding(16.dp), shape = RoundedCornerShape(28.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHigh) {
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(stringResource(R.string.capture_title), style = MaterialTheme.typography.titleLarge)
                        OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().focusRequester(focus),
                            placeholder = { Text(stringResource(R.string.idea_jot_tags)) }, minLines = 2,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { save() }))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            TextButton(onClick = ::finish) { Text(stringResource(R.string.cancel)) }
                            Button(onClick = ::save, enabled = text.isNotBlank()) { Text(stringResource(R.string.save)) }
                        }
                    }
                }
            }
        }
    }
}
