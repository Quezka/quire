package io.github.quezka.quire.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Button
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.DEFAULT_SLEEP_HOURS
import io.github.quezka.quire.domain.DEFAULT_WAKE
import io.github.quezka.quire.domain.Sleep
import io.github.quezka.quire.domain.SleepLog
import java.time.LocalDate

private const val NIGHTS = 14L

@Composable
fun SleepScreen(container: Container, version: Int, back: () -> Unit) {
    val repo = container.repository
    val settings = container.settings
    val today = repo.today()
    var goalHours by remember { mutableStateOf(settings.get("sleep.hours")?.toDoubleOrNull() ?: DEFAULT_SLEEP_HOURS) }
    var goalWake by remember { mutableStateOf(settings.get("sleep.wake")?.toIntOrNull() ?: DEFAULT_WAKE) }
    var day by remember { mutableStateOf(today) }
    val logs = remember(version) { repo.sleepLogs().filter { it.day > today.minusDays(NIGHTS) && it.day <= today } }
    val stats = remember(logs, goalHours) { Sleep.stats(logs, goalHours) }

    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_sleep), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            TonightPanel(container, version) { day = today }
            NightPanel(repo, day, today, version) { day = it }
            Panel(stringResource(R.string.sleep_goal)) {
                var remind by remember { mutableStateOf(container.sleepNudge.remindEnabled()) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = {
                        goalHours = (goalHours - 0.5).coerceAtLeast(3.0); settings.set("sleep.hours", goalHours.toString())
                    }) { Text("−") }
                    Text(stringResource(R.string.sleep_hours_value, goalHours.toString()))
                    OutlinedButton(onClick = {
                        goalHours = (goalHours + 0.5).coerceAtMost(14.0); settings.set("sleep.hours", goalHours.toString())
                    }) { Text("+") }
                    TimeButton(stringResource(R.string.sleep_wake_at), goalWake,
                        { goalWake = it; settings.set("sleep.wake", it.toString()) })
                }
                Hint(stringResource(R.string.sleep_bed_by, minutes(Sleep.bedtimeFor(goalWake, goalHours)), minutes(goalWake)))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.sleep_remind), Modifier.weight(1f))
                    androidx.compose.material3.Switch(remind, { remind = it; container.sleepNudge.setRemind(it) })
                }
            }
            Panel(stringResource(R.string.sleep_two_weeks)) {
                if (logs.isEmpty()) Hint(stringResource(R.string.sleep_nothing))
                else {
                    SleepBars(logs, goalHours)
                    Text(stringResource(R.string.sleep_average, durationText(stats.averageMinutes)),
                        style = MaterialTheme.typography.titleSmall)
                    Hint(stringResource(R.string.sleep_enough, stats.enough, stats.nights))
                    when (stats.regularity) {
                        "steady" -> Hint(stringResource(R.string.sleep_steady))
                        "mixed" -> Hint(stringResource(R.string.sleep_mixed, stats.bedtimeSpread))
                        "irregular" -> Hint(stringResource(R.string.sleep_irregular, stats.bedtimeSpread))
                    }
                    if (stats.streak >= 2) Hint(stringResource(R.string.sleep_streak, stats.streak))
                    if (stats.shortfallMinutes > 0) Hint(stringResource(R.string.sleep_short, durationText(stats.shortfallMinutes)))
                    stats.averageBedtime?.let { Hint(stringResource(R.string.sleep_usually, minutes(it))) }
                }
            }
        }
    }
}

private fun durationText(minutes: Int) = if (minutes % 60 == 0) "${minutes / 60} h" else "${minutes / 60} h %02d".format(minutes % 60)

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun NightPanel(repo: io.github.quezka.quire.data.Repository, day: LocalDate, today: LocalDate,
                       version: Int, pickDay: (LocalDate) -> Unit) {
    val existing = remember(day, version) { repo.sleep(day) }
    var asleep by remember(day, existing) { mutableStateOf(existing?.asleep ?: 23 * 60) }
    var woke by remember(day, existing) { mutableStateOf(existing?.woke ?: 7 * 60) }
    var quality by remember(day, existing) { mutableStateOf(existing?.quality) }
    var note by remember(day, existing) { mutableStateOf(existing?.note.orEmpty()) }
    val log = SleepLog(day, asleep, woke, quality, note)
    Panel(stringResource(R.string.sleep_log_night)) {
        DateButton(day, today, pickDay)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TimeButton(stringResource(R.string.sleep_fell_asleep), asleep, { asleep = it })
            TimeButton(stringResource(R.string.sleep_woke_up), woke, { woke = it })
        }
        Text(if (log.valid()) stringResource(R.string.sleep_slept, durationText(log.minutes))
            else stringResource(R.string.sleep_invalid), color = if (log.valid()) MaterialTheme.colorScheme.onSurfaceVariant
            else MaterialTheme.colorScheme.error)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (n in 1..5) FilterChip(selected = quality == n, onClick = { quality = if (quality == n) null else n },
                label = { Text(n.toString()) })
        }
        OutlinedTextField(note, { note = it }, Modifier.fillMaxWidth(),
            placeholder = { Text(stringResource(R.string.sleep_note_hint)) })
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (existing != null) TextButton(onClick = { repo.deleteSleep(day) }) {
                Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
            }
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            Button(onClick = { repo.saveSleep(log) }, enabled = log.valid()) { Text(stringResource(R.string.sleep_save)) }
        }
    }
}

/** One tap when you go to bed and one when you wake: the night is logged without typing. */
@Composable
private fun TonightPanel(container: Container, version: Int, logged: () -> Unit) {
    val manager = container.sleepNudge
    var since by remember(version) { mutableStateOf(manager.asleepSince()) }
    var failed by remember { mutableStateOf(false) }
    Panel(stringResource(R.string.sleep_tonight)) {
        Hint(if (since != null) stringResource(R.string.sleep_asleep_since, minutes(since!!.hour * 60 + since!!.minute))
            else stringResource(R.string.sleep_tap_hint))
        if (failed) Text(stringResource(R.string.sleep_forgot), color = MaterialTheme.colorScheme.error)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (since == null) Button(onClick = { manager.goToSleep(); since = manager.asleepSince(); failed = false }) {
                Text(stringResource(R.string.sleep_going))
            } else {
                Button(onClick = {
                    if (manager.wakeUp() != null) { since = null; failed = false; logged() } else failed = true
                }) { Text(stringResource(R.string.sleep_awake)) }
                TextButton(onClick = { manager.cancel(); since = null; failed = false }) { Text(stringResource(R.string.cancel)) }
            }
        }
    }
}

@Composable
private fun SleepBars(logs: List<SleepLog>, goalHours: Double) {
    val good = MaterialTheme.colorScheme.primary
    val bad = MaterialTheme.colorScheme.error
    val line = MaterialTheme.colorScheme.outlineVariant
    val top = maxOf(goalHours * 60 + 60, (logs.maxOf { it.minutes } + 30).toDouble())
    Canvas(Modifier.fillMaxWidth().height(140.dp)) {
        val goalY = (size.height - goalHours * 60 / top * size.height).toFloat()
        drawLine(line, Offset(0f, goalY), Offset(size.width, goalY), strokeWidth = 2f)
        val slot = size.width / logs.size
        logs.forEachIndexed { i, night ->
            val h = (night.minutes / top * size.height).toFloat()
            drawRoundRect(if (night.minutes >= goalHours * 60 * 0.9) good else bad,
                Offset(i * slot + slot * 0.2f, size.height - h), Size(slot * 0.6f, h), CornerRadius(8f))
        }
    }
}
