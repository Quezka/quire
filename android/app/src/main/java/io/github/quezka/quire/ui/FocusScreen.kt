package io.github.quezka.quire.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.FocusSettings
import io.github.quezka.quire.domain.Phase
import io.github.quezka.quire.domain.focusStats
import kotlinx.coroutines.delay

/** The Pomodoro timer: it keeps running (and notifies) while the app is closed. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FocusScreen(container: Container, version: Int, back: () -> Unit) {
    val focus = container.focus
    val repo = container.repository
    val changes by focus.changes.collectAsState()
    val timer = focus.timer
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(timer.running, changes) {
        while (true) {
            now = System.currentTimeMillis()
            focus.tick(announce = false)
            delay(200)
        }
    }
    val instant = java.time.Instant.ofEpochMilli(now)
    val remaining = timer.remaining(instant)
    val progress by animateFloatAsState(timer.progress(instant), tween(250), label = "ring")
    val phaseColor by animateColorAsState(when (timer.phase) {
        Phase.WORK -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.tertiary
    }, tween(Motion.MEDIUM), label = "phase")
    val track = MaterialTheme.colorScheme.surfaceVariant
    val stats = remember(version) { focusStats(repo.focusSessions(), repo.today()) }
    val context = LocalContext.current

    Column(Modifier.fillMaxSize()) {
        PageBar(stringResource(R.string.nav_focus), back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            AnimatedContent(timer.phase, transitionSpec = { fadeIn(tween(Motion.MEDIUM)).togetherWith(fadeOut(tween(Motion.SHORT))) },
                label = "phase-name") { phase ->
                Text(stringResource(when (phase) {
                    Phase.WORK -> R.string.phase_focus
                    Phase.SHORT_BREAK -> R.string.phase_short_break
                    Phase.LONG_BREAK -> R.string.phase_long_break
                }), style = MaterialTheme.typography.titleMedium, color = phaseColor)
            }
            Box(Modifier.size(260.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.fillMaxSize()) {
                    val stroke = 14.dp.toPx()
                    val inset = stroke / 2
                    val arc = Size(size.width - stroke, size.height - stroke)
                    drawArc(track, -90f, 360f, false, Offset(inset, inset), arc, style = Stroke(stroke))
                    drawArc(phaseColor, -90f, 360f * progress, false, Offset(inset, inset), arc,
                        style = Stroke(stroke, cap = StrokeCap.Round))
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val secs = remaining.seconds
                    Text("%02d:%02d".format(secs / 60, secs % 60), style = MaterialTheme.typography.displayMedium,
                        fontWeight = FontWeight.Bold)
                    Text(stringResource(R.string.round_of, timer.round, timer.settings.rounds),
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = focus::reset) { Icon(Icons.Filled.Refresh, stringResource(R.string.reset)) }
                FilledIconButton(onClick = focus::toggle, Modifier.size(72.dp)) {
                    AnimatedContent(timer.running, label = "play") { running ->
                        Icon(if (running) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                            stringResource(if (running) R.string.pause else R.string.start), Modifier.size(36.dp))
                    }
                }
                IconButton(onClick = focus::skip) { Icon(Icons.Filled.SkipNext, stringResource(R.string.skip)) }
            }

            Panel(stringResource(R.string.working_on), Modifier.fillMaxWidth()) {
                val tasks = remember(version) {
                    val today = repo.today()
                    repo.tasks().filter { !it.done && (it.due == null || it.due <= today.plusDays(14)) }
                        .sortedWith(compareBy({ it.due == null }, { it.due }, { it.title.lowercase() }))
                }
                var open by remember { mutableStateOf(false) }
                val current = focus.taskUid?.let(repo::task)
                ExposedDropdownMenuBox(open, { open = it }) {
                    OutlinedTextField(current?.title ?: focus.project.ifEmpty { stringResource(R.string.nothing_in_particular) },
                        {}, readOnly = true, label = { Text(stringResource(R.string.task)) },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
                        modifier = Modifier.fillMaxWidth().menuAnchor())
                    ExposedDropdownMenu(open, { open = false }) {
                        DropdownMenuItem(text = { Text(stringResource(R.string.nothing_in_particular)) },
                            onClick = { focus.focusOn(null); open = false })
                        for (t in tasks) DropdownMenuItem(text = { Text(t.title) },
                            onClick = { focus.focusOn(t.uid); open = false })
                    }
                }
                var project by remember(changes) { mutableStateOf(focus.project) }
                if (current == null) OutlinedTextField(project, { project = it; focus.focusOn(null, it) },
                    Modifier.fillMaxWidth(), singleLine = true, label = { Text(stringResource(R.string.or_a_project)) })
            }

            Panel(stringResource(R.string.focus_stats), Modifier.fillMaxWidth()) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile(stringResource(R.string.today), hoursText(stats.todayMinutes),
                        context.resources.getQuantityString(R.plurals.sessions, stats.todaySessions, stats.todaySessions),
                        Modifier.weight(1f))
                    StatTile(stringResource(R.string.this_week), hoursText(stats.weekMinutes),
                        context.resources.getQuantityString(R.plurals.sessions, stats.weekSessions, stats.weekSessions),
                        Modifier.weight(1f))
                }
                for ((label, minutes) in stats.todayByProject) Row {
                    Text(label, Modifier.weight(1f)); Text(hoursText(minutes), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            FocusSettingsPanel(timer.settings) { focus.saveSettings(it) }
        }
    }
}

@Composable
private fun FocusSettingsPanel(settings: FocusSettings, save: (FocusSettings) -> Unit) {
    Panel(stringResource(R.string.timer_settings), Modifier.fillMaxWidth()) {
        @Composable
        fun number(label: Int, value: Int, range: IntRange, set: (Int) -> FocusSettings) {
            var text by remember(value) { mutableStateOf(value.toString()) }
            OutlinedTextField(text, {
                text = it.filter(Char::isDigit).take(3)
                text.toIntOrNull()?.takeIf { v -> v in range }?.let { v -> save(set(v)) }
            }, Modifier.fillMaxWidth(), singleLine = true, label = { Text(stringResource(label)) },
                isError = text.toIntOrNull()?.let { it !in range } ?: true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        }
        number(R.string.focus_minutes, settings.workMinutes, 1..180) { settings.copy(workMinutes = it) }
        number(R.string.short_break_minutes, settings.shortBreakMinutes, 1..60) { settings.copy(shortBreakMinutes = it) }
        number(R.string.long_break_minutes, settings.longBreakMinutes, 1..120) { settings.copy(longBreakMinutes = it) }
        number(R.string.rounds_before_long_break, settings.rounds, 1..12) { settings.copy(rounds = it) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.auto_continue), Modifier.weight(1f))
            Switch(settings.autoContinue, { save(settings.copy(autoContinue = it)) })
        }
    }
}
