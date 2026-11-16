package io.github.quezka.quire.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.DayPlan
import io.github.quezka.quire.domain.Event
import java.time.LocalDate

/** Plan my day: suggested blocks for the day's tasks; untick what you don't want, the rest become events. */
@Composable
fun PlanDayDialog(repo: Repository, day: LocalDate, done: (Int) -> Unit, dismiss: () -> Unit) {
    val slots = remember(day) {
        val now = repo.now()
        DayPlan.suggest(repo.day(day), if (day == now.toLocalDate()) now.hour * 60 + now.minute else null)
    }
    val kept = remember(day) { mutableStateListOf(*Array(slots.size) { true }) }
    AlertDialog(
        onDismissRequest = dismiss,
        title = { Text(stringResource(R.string.plan_my_day)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(if (slots.isEmpty()) R.string.plan_nothing else R.string.plan_intro))
                slots.forEachIndexed { i, s ->
                    Row(Modifier.fillMaxWidth().clickable { kept[i] = !kept[i] }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(kept[i], { kept[i] = it })
                        Text("${minutes(s.start)}–${minutes(s.end)}  ${s.title}")
                    }
                }
            }
        },
        confirmButton = {
            if (slots.isNotEmpty()) TextButton({
                val chosen = slots.filterIndexed { i, _ -> kept[i] }
                for (s in chosen) repo.saveEvent(Event(Codec.newUid(), day, s.start, s.end, s.title, color = "#5b5bd6"))
                done(chosen.size)
            }) { Text(stringResource(R.string.plan_add)) }
        },
        dismissButton = { TextButton(dismiss) { Text(stringResource(android.R.string.cancel)) } },
    )
}
