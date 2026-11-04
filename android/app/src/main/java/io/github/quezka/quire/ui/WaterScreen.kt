package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.WATER_MAX_SIP
import io.github.quezka.quire.domain.Water
import io.github.quezka.quire.domain.WaterProfile
import java.time.LocalDate

@Composable
fun WaterScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val manager = container.water
    val today = repo.today()
    var profile by remember { mutableStateOf(manager.profile()) }
    val goal = profile.goal
    var picked by remember { mutableStateOf<LocalDate?>(null) }
    val shown = picked?.takeIf { it != today }  // null: today
    val logs = remember(version) { repo.waterLogs() }
    val entries = logs.filter { it.day == (shown ?: today) }
    val drunk = entries.sumOf { it.ml }
    val perDay = logs.groupBy { it.day }.mapValues { (_, l) -> l.sumOf { it.ml } }
    val week = (6L downTo 0L).map { today.minusDays(it) }.map { d -> d to (perDay[d] ?: 0) }

    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_water), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Panel(if (shown == null) stringResource(R.string.water_today) else shown.toString()) {
                if (shown != null) TextButton(onClick = { picked = null }) { Text(stringResource(R.string.water_back_today)) }
                if (goal == null) Hint(stringResource(R.string.water_set_profile)) else {
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(progress = { (drunk.toFloat() / goal).coerceIn(0f, 1f) },
                            modifier = Modifier.size(160.dp), strokeWidth = 14.dp)
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("$drunk ml", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                            Text(stringResource(R.string.water_of, goal), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    val behind = if (shown == null) Water.expected(goal, repo.now().let { it.hour * 60 + it.minute }, profile.start, profile.end) - drunk else 0
                    Hint(if (drunk >= goal) stringResource(R.string.water_reached)
                        else if (behind >= 250) stringResource(R.string.water_behind, behind)
                        else stringResource(R.string.water_to_go, goal - drunk))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { repo.addWater(profile.glass, shown) }) { Text("+${profile.glass} ml") }
                    OutlinedButton(onClick = { repo.addWater(150, shown) }) { Text("+150") }
                    OutlinedButton(onClick = { repo.addWater(500, shown) }) { Text("+500") }
                }
                var other by remember { mutableStateOf("") }
                val amount = other.toIntOrNull()?.takeIf { it in 1..WATER_MAX_SIP }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(other, { other = it }, Modifier.weight(1f), singleLine = true,
                        label = { Text(stringResource(R.string.water_other)) },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                    OutlinedButton(onClick = { repo.addWater(amount!!, shown); other = "" }, enabled = amount != null) {
                        Text(stringResource(R.string.water_add))
                    }
                    if (entries.isNotEmpty()) TextButton(onClick = { repo.deleteWater(entries.last().uid) }) {
                        Text(stringResource(R.string.water_undo))
                    }
                }
                for (e in entries.asReversed().take(5)) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${minutes(e.at)}   +${e.ml} ml", Modifier.weight(1f))
                    TextButton(onClick = { repo.deleteWater(e.uid) }) { Text(stringResource(R.string.delete)) }
                }
            }
            Panel(stringResource(R.string.water_week)) {
                WeekBars(week, goal, shown ?: today) { picked = it }
                if (goal != null) {
                    val streak = Water.streak((0L..120L).map { perDay[today.minusDays(it)] ?: 0 }, goal)
                    if (streak >= 2) Hint(stringResource(R.string.water_streak, streak))
                    Hint(stringResource(R.string.water_on_goal, week.count { it.second >= goal }))
                }
                val average = (1L..7L).sumOf { perDay[today.minusDays(it)] ?: 0 } / 7
                if (average > 0) Hint(stringResource(R.string.water_average, average))
            }
            ProfilePanel(profile) { profile = it; manager.save(it) }
        }
    }
}

@Composable
private fun ProfilePanel(profile: WaterProfile, save: (WaterProfile) -> Unit) {
    var height by remember { mutableStateOf(profile.heightCm?.toInt()?.toString().orEmpty()) }
    var weight by remember { mutableStateOf(profile.weightKg?.toString()?.removeSuffix(".0").orEmpty()) }
    var glass by remember { mutableStateOf(profile.glass.toString()) }
    var remind by remember { mutableStateOf(profile.remind) }
    var start by remember { mutableStateOf(profile.start) }
    var end by remember { mutableStateOf(profile.end) }
    var manual by remember { mutableStateOf(profile.manualGoal?.toString().orEmpty()) }
    val h = height.toDoubleOrNull(); val w = weight.replace(',', '.').toDoubleOrNull()
    val g = glass.toIntOrNull()
    val chosen = manual.toIntOrNull()
    val manualOk = manual.isBlank() || chosen in 500..6000
    val body = if (h != null && w != null) Water.goal(h, w) else null
    val valid = (body != null || (chosen != null && manualOk)) && manualOk && g != null && g in 50..1000 && start < end
    Panel(stringResource(R.string.water_goal)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(height, { height = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.water_height)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            OutlinedTextField(weight, { weight = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.water_weight)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
            OutlinedTextField(glass, { glass = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.water_glass)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        }
        OutlinedTextField(manual, { manual = it }, Modifier.fillMaxWidth(), singleLine = true,
            label = { Text(stringResource(R.string.water_manual)) }, isError = !manualOk,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.water_remind), Modifier.weight(1f))
            Switch(remind, { remind = it })
        }
        if (remind) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TimeButton(stringResource(R.string.from), start, { start = it })
            TimeButton(stringResource(R.string.to), end, { end = it })
        }
        if (valid) Hint(stringResource(R.string.water_goal_is, chosen ?: body!!))
        Button(onClick = { save(WaterProfile(h, w, g!!, remind, start, end, chosen)) }, enabled = valid) {
            Text(stringResource(R.string.save))
        }
    }
}

@Composable
private fun WeekBars(week: List<Pair<LocalDate, Int>>, goal: Int?, selected: LocalDate, pick: (LocalDate) -> Unit) {
    val good = MaterialTheme.colorScheme.tertiary
    val normal = MaterialTheme.colorScheme.primary
    DayBars(week.map { (d, ml) ->
        DayBar(d, ml, if (goal != null && ml >= goal) good else normal, if (ml > 0) "%.1f".format(ml / 1000.0) else "")
    }, goal ?: 0, selected, pick, height = 110)
}
