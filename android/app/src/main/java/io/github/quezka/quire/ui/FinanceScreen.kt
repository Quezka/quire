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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.domain.Finance
import io.github.quezka.quire.domain.Transaction
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

private fun cents(value: Long) = money(value / 100.0)

@Composable
fun FinanceScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val context = LocalContext.current
    var month by remember { mutableStateOf(YearMonth.from(repo.today())) }
    val items = remember(version, month) { repo.transactions(month.atDay(1), month.atEndOfMonth()) }
    val income = items.filter { it.income }.sumOf { it.cents }
    val spent = items.filter { !it.income }.sumOf { it.cents }
    val categories = remember(items) { Finance.byCategory(items) }
    var editing by remember { mutableStateOf<Transaction?>(null) }
    var adding by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_money), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { month = month.minusMonths(1) }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, stringResource(R.string.money_previous))
                }
                Text(month.format(DateTimeFormatter.ofPattern("LLLL yyyy", Locale.getDefault()))
                    .replaceFirstChar { it.titlecase(Locale.getDefault()) },
                    Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                IconButton(onClick = { month = month.plusMonths(1) }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, stringResource(R.string.money_next))
                }
            }
            Panel(stringResource(R.string.money_balance)) {
                Text(cents(income - spent), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold,
                    color = if (income - spent < 0) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
                Hint("${stringResource(R.string.money_received)} ${cents(income)} · ${stringResource(R.string.money_spent)} ${cents(spent)}")
                Button(onClick = { adding = true }) { Text(stringResource(R.string.money_add)) }
            }
            if (categories.isNotEmpty()) Panel(stringResource(R.string.money_where)) {
                val top = categories.first().second.toFloat()
                for ((name, value) in categories) Column(Modifier.padding(vertical = 2.dp)) {
                    Row { Text(name.ifBlank { context.getString(R.string.money_no_category) }, Modifier.weight(1f)); Text(cents(value)) }
                    LinearProgressIndicator(progress = { value / top }, Modifier.fillMaxWidth().padding(top = 2.dp))
                }
            }
            Panel(stringResource(R.string.money_entries)) {
                if (items.isEmpty()) Hint(stringResource(R.string.money_none))
                for (t in items.asReversed()) Row(Modifier.fillMaxWidth().clickable { editing = t }.padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t.category.ifBlank { context.getString(R.string.money_no_category) }, fontWeight = FontWeight.SemiBold)
                        Hint(listOf(relativeDate(context, t.day, repo.today()), t.note).filter { it.isNotBlank() }.joinToString(" · "))
                    }
                    Text((if (t.income) "+" else "−") + cents(t.cents),
                        color = if (t.income) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)
                }
            }
        }
    }
    if (adding || editing != null) TransactionEditor(editing, repo.today(), repo.transactionCategories(), {
        repo.saveTransaction(it); adding = false; editing = null
    }, editing?.let { t -> { repo.deleteTransaction(t.uid); editing = null } }) { adding = false; editing = null }
}

@Composable
private fun TransactionEditor(existing: Transaction?, today: LocalDate, categories: List<String>,
                              save: (Transaction) -> Unit, delete: (() -> Unit)?, close: () -> Unit) {
    var amount by remember { mutableStateOf(existing?.let { "${it.cents / 100},${"%02d".format(it.cents % 100)}" }.orEmpty()) }
    var income by remember { mutableStateOf(existing?.income ?: false) }
    var category by remember { mutableStateOf(existing?.category.orEmpty()) }
    var note by remember { mutableStateOf(existing?.note.orEmpty()) }
    var date by remember { mutableStateOf(existing?.day ?: today) }
    val parsed = Finance.parseCents(amount)?.takeIf { it in 1..Finance.MAX_CENTS }
    AlertDialog(onDismissRequest = close,
        title = { Text(stringResource(if (existing == null) R.string.money_add else R.string.money_edit)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.money_is_income), Modifier.weight(1f))
                    Switch(income, { income = it })
                }
                OutlinedTextField(amount, { amount = it }, label = { Text(stringResource(R.string.money_amount)) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    isError = amount.isNotBlank() && parsed == null)
                DateButton(date, today, { date = it })
                OutlinedTextField(category, { category = it }, label = { Text(stringResource(R.string.money_category)) }, singleLine = true)
                for (c in categories.filter { it != category && it.contains(category, ignoreCase = true) }.take(4))
                    TextButton(onClick = { category = c }) { Text(c) }
                OutlinedTextField(note, { note = it }, label = { Text(stringResource(R.string.money_note)) }, singleLine = true)
                delete?.let { TextButton(onClick = it) { Text(stringResource(R.string.delete)) } }
            }
        },
        confirmButton = {
            TextButton(enabled = parsed != null, onClick = {
                save(Transaction(existing?.uid ?: Codec.newUid(), date, parsed!!, income, category.trim(), note.trim()))
            }) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = close) { Text(stringResource(R.string.cancel)) } })
}
