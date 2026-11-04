package io.github.quezka.quire.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.domain.Doses
import io.github.quezka.quire.domain.Medicine

@Composable
fun MedicineScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val today = repo.today()
    val minute = repo.now().let { it.hour * 60 + it.minute }
    val medicines = remember(version) { repo.medicines() }
    val plan = remember(version) { Doses.plan(today, medicines, repo.doseLogs()) }
    var editing by remember { mutableStateOf<Medicine?>(null) }
    var adding by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_medicine), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Panel(stringResource(R.string.today)) {
                if (plan.isEmpty()) Hint(stringResource(R.string.medicine_none_today))
                for (d in plan) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(d.log?.taken == true, { on ->
                        if (on) repo.markDose(d.medicine.uid, today, d.planned, true) else repo.unmarkDose(d.medicine.uid, today, d.planned)
                    })
                    Column(Modifier.weight(1f)) {
                        Text("${minutes(d.planned)}  ${d.medicine.name}", fontWeight = FontWeight.SemiBold)
                        val state = when {
                            d.log?.taken == true -> stringResource(R.string.medicine_taken_at, minutes(d.log.at))
                            d.log != null -> stringResource(R.string.medicine_skipped)
                            Doses.isLate(d, minute) -> stringResource(R.string.medicine_late)
                            else -> ""
                        }
                        val line = listOf(d.medicine.dose, state).filter { it.isNotBlank() }.joinToString(" · ")
                        if (line.isNotEmpty()) Text(line, style = MaterialTheme.typography.bodySmall,
                            color = if (Doses.isLate(d, minute)) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (!d.done) TextButton(onClick = { repo.markDose(d.medicine.uid, today, d.planned, false) }) {
                        Text(stringResource(R.string.medicine_skip))
                    }
                }
            }
            Panel(stringResource(R.string.medicine_yours)) {
                for (m in medicines) Column(Modifier.fillMaxWidth().clickable { editing = m }.padding(vertical = 6.dp)) {
                    Text(m.name, fontWeight = FontWeight.SemiBold)
                    Hint(listOfNotNull(m.dose.ifBlank { null }, m.times.joinToString(", ") { minutes(it) }.ifBlank { null },
                        if (m.active) null else stringResource(R.string.medicine_stopped)).joinToString(" · "))
                }
                Button(onClick = { adding = true }) { Text(stringResource(R.string.medicine_add)) }
                Hint(stringResource(R.string.medicine_disclaimer))
            }
        }
    }
    if (adding || editing != null) MedicineEditor(editing, {
        repo.saveMedicine(it); container.medicines.plan(); adding = false; editing = null
    }, editing?.let { m -> { repo.deleteMedicine(m.uid); container.medicines.plan(); editing = null } }) {
        adding = false; editing = null
    }
}

@Composable
private fun MedicineEditor(existing: Medicine?, save: (Medicine) -> Unit, delete: (() -> Unit)?, close: () -> Unit) {
    var name by remember { mutableStateOf(existing?.name.orEmpty()) }
    var dose by remember { mutableStateOf(existing?.dose.orEmpty()) }
    var times by remember { mutableStateOf(existing?.times.orEmpty().joinToString(", ") { minutes(it) }) }
    var active by remember { mutableStateOf(existing?.active ?: true) }
    val parsed = Doses.parseTimes(times)
    AlertDialog(onDismissRequest = close,
        title = { Text(stringResource(if (existing == null) R.string.medicine_add else R.string.medicine_edit)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text(stringResource(R.string.medicine_name)) }, singleLine = true)
                OutlinedTextField(dose, { dose = it }, label = { Text(stringResource(R.string.medicine_dose)) }, singleLine = true)
                OutlinedTextField(times, { times = it }, label = { Text(stringResource(R.string.medicine_times)) },
                    placeholder = { Text("8:00, 20:00") }, singleLine = true, isError = parsed == null)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.medicine_taking), Modifier.weight(1f))
                    Switch(active, { active = it })
                }
                delete?.let { TextButton(onClick = it) { Text(stringResource(R.string.delete)) } }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && parsed != null, onClick = {
                save((existing ?: Medicine(Codec.newUid(), "")).copy(name = name.trim(), dose = dose.trim(),
                    times = parsed.orEmpty(), active = active))
            }) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = close) { Text(stringResource(R.string.cancel)) } })
}
