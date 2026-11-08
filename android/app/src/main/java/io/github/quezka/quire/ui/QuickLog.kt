package io.github.quezka.quire.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material.icons.filled.Savings
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.domain.Doses
import io.github.quezka.quire.domain.Finance
import io.github.quezka.quire.domain.Transaction

/** Something just logged, and how to take it back. */
class Logged(val message: String, val undo: (() -> Unit)?)

/**
 * The main page's quick log: drank water, going to sleep / woke up, took a medicine, an expense. A tap logs it
 * through the same rules as the Water, Sleep, Medicines and Money pages; a long press offers choices.
 */
@Composable
fun QuickLog(container: Container, version: Int, logged: (Logged) -> Unit) {
    val repo = container.repository
    val today = repo.today()
    val profile = remember(version) { container.water.profile() }
    val drunk = remember(version) { repo.waterOn(today).sumOf { it.ml } }
    val since = remember(version) { container.sleepNudge.asleepSince() }
    val pending = remember(version) { Doses.pending(Doses.plan(today, repo.medicines(), repo.doseLogs())) }
    var spending by remember { mutableStateOf(false) }
    val litres = { ml: Int -> String.format(java.util.Locale.getDefault(), "%.1f", ml / 1000.0) }

    val drink = stringResource(R.string.quick_logged_water)
    val night = stringResource(R.string.quick_good_night)
    val morning = stringResource(R.string.quick_good_morning)
    val forgot = stringResource(R.string.sleep_forgot)
    val took = stringResource(R.string.quick_took_done)
    val spent = stringResource(R.string.quick_spent)

    fun addWater(ml: Int) {
        val uid = repo.addWater(ml)
        logged(Logged(String.format(drink, ml)) { repo.deleteWater(uid) })
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            QuickTile(Icons.Filled.WaterDrop, stringResource(R.string.quick_water),
                if (profile.goal != null) "${litres(drunk)} / ${litres(profile.goal!!)} l" else "${litres(drunk)} l",
                Modifier.weight(1f),
                choices = listOf(150, 250, 500).map { ml -> "+$ml ml" to { addWater(ml) } },
            ) { addWater(profile.glass) }
            if (since == null) {
                QuickTile(Icons.Filled.Bedtime, stringResource(R.string.quick_sleep), stringResource(R.string.quick_going_to_bed),
                    Modifier.weight(1f)) {
                    container.sleepNudge.goToSleep()
                    repo.refreshed()
                    logged(Logged(night) { container.sleepNudge.cancel(); repo.refreshed() })
                }
            } else {
                QuickTile(Icons.Filled.WbSunny, stringResource(R.string.quick_sleep), stringResource(R.string.quick_woke_up),
                    Modifier.weight(1f)) {
                    val log = container.sleepNudge.wakeUp()
                    if (log == null) logged(Logged(forgot, null))
                    else logged(Logged(morning) { repo.deleteSleep(log.day) })
                    repo.refreshed()
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val next = pending.firstOrNull()
            QuickTile(Icons.Filled.Medication, stringResource(R.string.quick_medicines),
                if (next != null) stringResource(R.string.quick_took, next.medicine.name) else stringResource(R.string.quick_none_due),
                Modifier.weight(1f), enabled = next != null,
                choices = if (pending.size > 1) pending.map { d ->
                    "${d.medicine.name} · ${minutes(d.planned)}" to {
                        repo.markDose(d.medicine.uid, d.day, d.planned, true)
                        logged(Logged(String.format(took, d.medicine.name)) { repo.unmarkDose(d.medicine.uid, d.day, d.planned) })
                    }
                } else emptyList(),
            ) {
                if (next != null) {
                    repo.markDose(next.medicine.uid, next.day, next.planned, true)
                    logged(Logged(String.format(took, next.medicine.name)) { repo.unmarkDose(next.medicine.uid, next.day, next.planned) })
                }
            }
            QuickTile(Icons.Filled.Savings, stringResource(R.string.quick_money), stringResource(R.string.quick_add_expense),
                Modifier.weight(1f)) { spending = true }
        }
    }
    if (spending) ExpenseDialog(onDismiss = { spending = false }) { cents, what ->
        val t = Transaction(Codec.newUid(), today, cents, income = false, note = what)
        repo.saveTransaction(t)
        spending = false
        logged(Logged(String.format(spent, money(cents / 100.0))) { repo.deleteTransaction(t.uid) })
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun QuickTile(icon: ImageVector, title: String, detail: String, modifier: Modifier = Modifier,
                      enabled: Boolean = true, choices: List<Pair<String, () -> Unit>> = emptyList(), onTap: () -> Unit) {
    val haptics = LocalHapticFeedback.current
    var menu by remember { mutableStateOf(false) }
    val c = MaterialTheme.colorScheme
    Box(modifier) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = if (enabled) c.primaryContainer.copy(alpha = Glass.tint) else c.surfaceVariant.copy(alpha = Glass.tint),
            contentColor = if (enabled) c.onPrimaryContainer else c.onSurfaceVariant,
            border = Glass.edge(),
            modifier = Modifier.fillMaxWidth().heightIn(min = 76.dp).combinedClickable(
                enabled = enabled,
                onClick = { haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove); onTap() },
                onLongClick = if (choices.isNotEmpty()) ({ haptics.performHapticFeedback(HapticFeedbackType.LongPress); menu = true }) else null,
            ),
        ) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, null, Modifier.size(28.dp))
                Column(Modifier.padding(start = 12.dp)) {
                    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, maxLines = 1)
                    Text(detail, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        DropdownMenu(menu, onDismissRequest = { menu = false }) {
            for ((label, action) in choices) DropdownMenuItem(text = { Text(label) }, onClick = { menu = false; action() })
        }
    }
}

@Composable
private fun ExpenseDialog(onDismiss: () -> Unit, onSave: (Long, String) -> Unit) {
    var amount by remember { mutableStateOf("") }
    var what by remember { mutableStateOf("") }
    val cents = Finance.parseCents(amount)?.takeIf { it > 0 }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.quick_add_expense_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(amount, { amount = it }, label = { Text(stringResource(R.string.quick_amount)) },
                    singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                OutlinedTextField(what, { what = it }, label = { Text(stringResource(R.string.quick_what_for)) }, singleLine = true)
                if (amount.isNotBlank() && cents == null) Text(stringResource(R.string.quick_not_amount),
                    color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Start)
            }
        },
        confirmButton = { TextButton(onClick = { cents?.let { onSave(it, what.trim()) } }, enabled = cents != null) { Text(stringResource(R.string.save)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
    )
}
