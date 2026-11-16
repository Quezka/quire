package io.github.quezka.quire.capture

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.container
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.domain.Assistant
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.ui.QuireTheme
import io.github.quezka.quire.ui.minutes

/** The evening check-in: see what's on tomorrow and pick the one main thing (it comes first in the morning digest,
 *  on Today and on the lock screen). One tap, or type something new. */
class PlanTomorrowActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val c = container
        val today = c.repository.today()
        val tomorrow = today.plusDays(1)
        val agenda = c.repository.day(tomorrow).items.sortedBy { it.start }.take(5)
        val candidates = Assistant.planCandidates(c.repository.tasks(), today)
        setContent {
            QuireTheme {
                var picked by remember { mutableStateOf(c.assistant.mainFor(tomorrow)) }
                var other by remember { mutableStateOf("") }
                fun save() {
                    val uid = if (other.isNotBlank()) c.repository.saveTask(Task(Codec.newUid(), other.trim(), due = tomorrow)).uid
                    else picked
                    c.assistant.setMain(tomorrow, uid)
                    finish()
                }
                Surface(Modifier.fillMaxWidth().padding(16.dp), shape = RoundedCornerShape(28.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHigh) {
                    Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(stringResource(R.string.plan_title), style = MaterialTheme.typography.titleLarge)
                        if (agenda.isEmpty()) Text(stringResource(R.string.digest_free_tomorrow), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        for (item in agenda) Text("${minutes(item.start)}  ${item.title}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(stringResource(R.string.plan_pick), style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
                        for (task in candidates) Row(Modifier.fillMaxWidth().clickable { picked = task.uid; other = "" },
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(picked == task.uid && other.isBlank(), { picked = task.uid; other = "" })
                            Text(task.title, style = MaterialTheme.typography.bodyLarge)
                        }
                        OutlinedTextField(other, { other = it }, Modifier.fillMaxWidth(),
                            placeholder = { Text(stringResource(R.string.plan_other)) }, singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done), keyboardActions = KeyboardActions(onDone = { save() }))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            TextButton(onClick = ::finish) { Text(stringResource(R.string.cancel)) }
                            TextButton(onClick = ::save, enabled = picked != null || other.isNotBlank()) { Text(stringResource(R.string.save)) }
                        }
                    }
                }
            }
        }
    }
}
