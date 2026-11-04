package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
    val lastNight = logs.firstOrNull { it.day == today }
    val stats = remember(logs, goalHours) { Sleep.stats(logs, goalHours) }

    Column(Modifier.fillMaxSize().imePadding()) {
        PageBar(stringResource(R.string.nav_sleep), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            TonightPanel(container, version, lastNight, Sleep.bedtimeFor(goalWake, goalHours)) { day = today }
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
                    SleepBars(logs, goalHours, today, day) { day = it }
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
                    stats.averageQuality?.let { Hint(stringResource(R.string.sleep_average_quality, "%.1f".format(it))) }
                    Sleep.weekBefore(logs, today)?.let { before ->
                        val change = stats.averageMinutes - before
                        if (kotlin.math.abs(change) >= 10) Hint(stringResource(
                            if (change > 0) R.string.sleep_more_than_before else R.string.sleep_less_than_before,
                            durationText(kotlin.math.abs(change))))
                    }
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
private fun TonightPanel(container: Container, version: Int, lastNight: SleepLog?, bedtime: Int, logged: () -> Unit) {
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
        if (lastNight != null) {
            Text(stringResource(R.string.sleep_last_night, durationText(lastNight.minutes), minutes(lastNight.asleep), minutes(lastNight.woke)),
                style = MaterialTheme.typography.titleSmall)
            if (lastNight.quality == null) {
                Hint(stringResource(R.string.sleep_how_was_it))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (n in 1..5) FilterChip(selected = false, onClick = { container.repository.saveSleep(lastNight.copy(quality = n)) },
                        label = { Text(n.toString()) })
                }
            } else Hint(stringResource(R.string.sleep_rated, lastNight.quality))
        }
        val now = container.repository.now()
        val left = Sleep.minutesUntil(now.hour * 60 + now.minute, bedtime)
        if (since == null && left <= 6 * 60) Hint(stringResource(R.string.sleep_bedtime_in, minutes(bedtime), durationText(left)))
    }
}

@Composable
private fun SleepBars(logs: List<SleepLog>, goalHours: Double, today: LocalDate, selected: LocalDate, pick: (LocalDate) -> Unit) {
    val good = MaterialTheme.colorScheme.primary
    val bad = MaterialTheme.colorScheme.error
    val goal = (goalHours * 60).toInt()
    val bars = (NIGHTS - 1 downTo 0L).map { today.minusDays(it) }.map { d ->
        val night = logs.firstOrNull { it.day == d }
        DayBar(d, night?.minutes ?: 0, if (night != null && night.minutes >= goal * 0.9) good else bad,
            night?.let { "%.0f".format(it.minutes / 60.0) }.orEmpty())
    }
    DayBars(bars, goal, selected, pick)
}
