package io.github.quezka.quire.ui

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.COURSE_COLORS
import io.github.quezka.quire.domain.ClassSlot
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.MINUTES_PER_DAY
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.ShiftPattern
import io.github.quezka.quire.domain.Work
import io.github.quezka.quire.domain.durationBetween
import io.github.quezka.quire.domain.netPay
import io.github.quezka.quire.domain.pay
import io.github.quezka.quire.domain.paidMinutes
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.TextStyle
import java.util.Locale

/** What tapping something on the timeline opens, and the "new event / new shift" sheets. */
@Composable
fun AgendaEditors(repo: Repository, editing: AgendaItem?, adding: ItemKind?, day: LocalDate, close: () -> Unit) {
    var weeklyChoice by remember(editing) { mutableStateOf(editing?.takeIf { it.kind == ItemKind.SHIFT && it.weekly }) }
    var replacing by remember(editing) { mutableStateOf<AgendaItem?>(null) }
    var schedule by remember(editing) { mutableStateOf<String?>(null) }
    when {
        adding == ItemKind.EVENT -> EventEditor(repo, null, day, close)
        adding == ItemKind.SHIFT -> ShiftEditor(repo, null, day, null, close)
        editing == null -> Unit
        editing.kind == ItemKind.EVENT -> EventEditor(repo, editing.refUid, day, close)
        editing.kind == ItemKind.CLASS -> editing.refUid?.let { CourseEditor(repo, it, close) }
        schedule != null -> JobEditor(repo, schedule, close)
        replacing != null -> ShiftEditor(repo, null, editing.originDay, editing, close)
        weeklyChoice != null -> WeeklyShiftDialog(
            onChange = { replacing = editing; weeklyChoice = null },
            onSkip = { repo.skipOccurrence(editing.refUid!!, editing.originDay, editing.originStart); close() },
            onSchedule = { schedule = editing.refUid; weeklyChoice = null },
            onDismiss = close)
        else -> ShiftEditor(repo, editing.refUid, editing.originDay, null, close)
    }
}

@Composable
private fun WeeklyShiftDialog(onChange: () -> Unit, onSkip: () -> Unit, onSchedule: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.weekly_shift)) },
        text = {
            Column {
                Hint(stringResource(R.string.weekly_shift_help))
                TextButton(onClick = onChange) { Text(stringResource(R.string.change_this_week)) }
                TextButton(onClick = onSkip) { Text(stringResource(R.string.skip_this_week)) }
                TextButton(onClick = onSchedule) { Text(stringResource(R.string.edit_weekly_schedule)) }
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}

// ---- shared pieces ----

/** A bottom sheet with a title and Save/Cancel (and Delete for an existing thing). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditorSheet(
    title: String,
    close: () -> Unit,
    canSave: Boolean,
    onSave: () -> Unit,
    onDelete: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(onDismissRequest = close, sheetState = sheet) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp)
            .verticalScroll(rememberScrollState()).animateContentSize(Motion.gentle()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            content()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (onDelete != null) TextButton(onClick = onDelete) {
                    Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
                }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = close) { Text(stringResource(R.string.cancel)) }
                Button(onClick = onSave, enabled = canSave) { Text(stringResource(R.string.save)) }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimeButton(label: String, minutes: Int, onPick: (Int) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    OutlinedButton(onClick = { open = true }, modifier) { Text("$label  ${minutes(minutes)}") }
    if (open) {
        val state = rememberTimePickerState(minutes / 60 % 24, minutes % 60, is24Hour = true)
        AlertDialog(onDismissRequest = { open = false },
            confirmButton = { TextButton(onClick = { onPick(state.hour * 60 + state.minute); open = false }) {
                Text(stringResource(R.string.ok)) } },
            dismissButton = { TextButton(onClick = { open = false }) { Text(stringResource(R.string.cancel)) } },
            text = { TimePicker(state) })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateButton(day: LocalDate, today: LocalDate, onPick: (LocalDate) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    val context = LocalContext.current
    OutlinedButton(onClick = { open = true }, modifier) { Text(relativeDate(context, day, today)) }
    if (open) {
        val state = rememberDatePickerState(day.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { open = false },
            confirmButton = { TextButton(onClick = {
                state.selectedDateMillis?.let { onPick(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }
                open = false
            }) { Text(stringResource(R.string.ok)) } },
            dismissButton = { TextButton(onClick = { open = false }) { Text(stringResource(R.string.cancel)) } },
        ) { DatePicker(state) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ColorPicker(selected: String, onPick: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        for (hex in COURSE_COLORS) {
            val chosen = hex.equals(selected, ignoreCase = true)
            val scale by animateFloatAsState(if (chosen) 1.15f else 1f, Motion.bouncy(), label = "swatch")
            Box(Modifier.size(32.dp).graphicsLayer { scaleX = scale; scaleY = scale }
                .background(parseColor(hex), CircleShape)
                .then(if (chosen) Modifier.border(3.dp, MaterialTheme.colorScheme.onSurface, CircleShape) else Modifier)
                .clickable { onPick(hex) })
        }
    }
}

fun weekdayName(weekday: Int, style: TextStyle = TextStyle.SHORT): String =
    DayOfWeek.of(weekday + 1).getDisplayName(style, Locale.getDefault())
        .replaceFirstChar { it.titlecase(Locale.getDefault()) }

@Composable
fun WeekdayChips(selected: Int, onPick: (Int) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for (d in 0..6) FilterChip(selected = selected == d, onClick = { onPick(d) },
            label = { Text(weekdayName(d, TextStyle.NARROW)) })
    }
}

// ---- events ----

@Composable
fun EventEditor(repo: Repository, uid: String?, day: LocalDate, close: () -> Unit) {
    val existing = remember(uid) { uid?.let(repo::event) }
    var title by remember { mutableStateOf(existing?.title.orEmpty()) }
    var date by remember { mutableStateOf(existing?.day ?: day) }
    var start by remember { mutableStateOf(existing?.start ?: 9 * 60) }
    var end by remember { mutableStateOf(existing?.end ?: 10 * 60) }
    var details by remember { mutableStateOf(existing?.details.orEmpty()) }
    var color by remember { mutableStateOf(existing?.color ?: "#8a8f98") }
    EditorSheet(stringResource(if (existing == null) R.string.new_event else R.string.edit_event), close,
        canSave = title.isNotBlank() && end > start,
        onSave = {
            repo.saveEvent(Event(existing?.uid ?: Codec.newUid(), date, start, end, title, details, color)); close()
        },
        onDelete = existing?.let { { repo.deleteEvent(it.uid); close() } }) {
        OutlinedTextField(title, { title = it }, Modifier.fillMaxWidth(),
            placeholder = { Text(stringResource(R.string.event_title_hint)) },
            textStyle = MaterialTheme.typography.titleMedium)
        DateButton(date, repo.today(), { date = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TimeButton(stringResource(R.string.from), start, { start = it; if (end <= it) end = minOf(it + 60, MINUTES_PER_DAY) })
            TimeButton(stringResource(R.string.to), end, { end = if (it == 0) MINUTES_PER_DAY else it })
        }
        if (end <= start) Text(stringResource(R.string.ends_before_start), color = MaterialTheme.colorScheme.error)
        ColorPicker(color) { color = it }
        OutlinedTextField(details, { details = it }, Modifier.fillMaxWidth().heightIn(min = 90.dp),
            label = { Text(stringResource(R.string.details)) })
    }
}

// ---- shifts ----

/** A one-off shift: new ([uid] null), existing, or standing in for a weekly occurrence. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShiftEditor(repo: Repository, uid: String?, day: LocalDate, replaces: AgendaItem?, close: () -> Unit) {
    val jobs = remember { repo.jobs() }
    val existing = remember(uid) { uid?.let(repo::shift) }
    var jobUid by remember { mutableStateOf(existing?.jobUid ?: replaces?.refUid ?: jobs.firstOrNull()?.uid) }
    var date by remember { mutableStateOf(existing?.day ?: day) }
    var start by remember { mutableStateOf(existing?.start ?: replaces?.originStart ?: 9 * 60) }
    val weeklyDuration = remember(replaces) {
        replaces?.let { r -> repo.job(r.refUid!!)?.patterns?.firstOrNull { it.occursOn(r.originDay) && it.start == r.originStart } }
    }
    var end by remember { mutableStateOf(((existing?.end ?: weeklyDuration?.let { it.start + it.duration } ?: (17 * 60))) % MINUTES_PER_DAY) }
    var breakText by remember { mutableStateOf((existing?.breakMinutes ?: weeklyDuration?.breakMinutes ?: 0).toString()) }
    var notes by remember { mutableStateOf(existing?.notes.orEmpty()) }
    var repeat by remember { mutableStateOf("0") }
    var newJob by remember { mutableStateOf(false) }
    val duration = durationBetween(start, end)
    val breakMinutes = breakText.toIntOrNull() ?: -1
    val problem = Work.problem(start, duration, breakMinutes)
    val job = jobs.firstOrNull { it.uid == jobUid }
    val preview = Shift(null, jobUid.orEmpty(), date, start, duration, breakMinutes.coerceAtLeast(0))

    if (newJob) { JobEditor(repo, null) { newJob = false; close() }; return }
    EditorSheet(stringResource(when {
        replaces != null -> R.string.change_this_week
        existing == null -> R.string.new_shift
        else -> R.string.edit_shift
    }), close, canSave = job != null && problem == null,
        onSave = {
            val shift = preview.copy(uid = existing?.uid, notes = notes)
            repo.saveShift(shift, if (existing == null && replaces == null) repeat.toIntOrNull() ?: 0 else 0,
                replaces?.let { it.originDay to it.originStart })
            close()
        },
        onDelete = existing?.let { { repo.deleteShift(it.uid!!); close() } }) {
        if (jobs.isEmpty()) {
            Hint(stringResource(R.string.no_jobs))
            OutlinedButton(onClick = { newJob = true }) { Text(stringResource(R.string.new_job)) }
            return@EditorSheet
        }
        var open by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
            OutlinedTextField(job?.name.orEmpty(), {}, readOnly = true, label = { Text(stringResource(R.string.job)) },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
                modifier = Modifier.fillMaxWidth().menuAnchor())
            ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                for (j in jobs) DropdownMenuItem(text = { Text(j.name) }, onClick = { jobUid = j.uid; open = false })
            }
        }
        DateButton(date, repo.today(), { date = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TimeButton(stringResource(R.string.from), start, { start = it })
            TimeButton(stringResource(R.string.to), end, { end = it })
        }
        OutlinedTextField(breakText, { breakText = it.filter(Char::isDigit).take(3) }, Modifier.fillMaxWidth(),
            label = { Text(stringResource(R.string.break_minutes)) }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        val context = LocalContext.current
        if (problem != null) Text(workMessage(context, problem), color = MaterialTheme.colorScheme.error)
        else {
            val gross = preview.pay(job?.hourlyRate)
            val parts = buildList {
                add(context.getString(R.string.paid_time, hoursText(preview.paidMinutes)))
                if (preview.end > MINUTES_PER_DAY) add(context.getString(R.string.ends_next_day))
                gross?.let { add(context.getString(R.string.pay_estimate, money(it), money(netPay(it, job?.deductions ?: 0.0)!!))) }
            }
            Hint(parts.joinToString(" · "))
        }
        if (existing == null && replaces == null) OutlinedTextField(repeat, { repeat = it.filter(Char::isDigit).take(2) },
            Modifier.fillMaxWidth(), singleLine = true, label = { Text(stringResource(R.string.repeat_weeks)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.notes)) })
    }
}

// ---- jobs ----

/** A job: name, colour, pay, and its weekly schedule (applied from this week on). */
@Composable
fun JobEditor(repo: Repository, uid: String?, close: () -> Unit) {
    val existing = remember(uid) { uid?.let(repo::job) }
    var name by remember { mutableStateOf(existing?.name.orEmpty()) }
    var color by remember { mutableStateOf(existing?.color ?: "#0090ff") }
    var rate by remember { mutableStateOf(existing?.hourlyRate?.let(::plainNumber).orEmpty()) }
    var deductions by remember { mutableStateOf(existing?.deductions?.takeIf { it > 0 }?.let(::plainNumber).orEmpty()) }
    val weekly = remember { mutableStateListOf<ShiftPattern>().apply {
        existing?.let { addAll(Work.activeSchedule(it, repo.today())) }
    } }
    var confirmDelete by remember { mutableStateOf(false) }
    val rateValue = rate.replace(',', '.').toDoubleOrNull()
    val deductionValue = deductions.replace(',', '.').toDoubleOrNull() ?: 0.0
    val valid = name.isNotBlank() && (rate.isBlank() || (rateValue != null && rateValue >= 0)) &&
        deductionValue in 0.0..100.0 && weekly.all { Work.problem(it.start, it.duration, it.breakMinutes) == null }

    EditorSheet(stringResource(if (existing == null) R.string.new_job else R.string.edit_job), close, valid,
        onSave = {
            val base = existing ?: Job(Codec.newUid(), "")
            repo.saveJob(base.copy(name = name, color = color, hourlyRate = rateValue, deductions = deductionValue),
                weekly.toList())
            close()
        },
        onDelete = existing?.let { { confirmDelete = true } }) {
        OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.job_name)) })
        ColorPicker(color) { color = it }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(rate, { rate = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.hourly_rate)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
            OutlinedTextField(deductions, { deductions = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.deductions_percent)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
        }
        SectionTitle(stringResource(R.string.weekly_schedule))
        Hint(stringResource(R.string.weekly_schedule_help))
        for ((i, p) in weekly.withIndex()) {
            Column(Modifier.fillMaxWidth().animateContentSize()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(weekdayName(p.weekday, TextStyle.FULL), Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    IconButton(onClick = { weekly.removeAt(i) }) { Icon(Icons.Filled.Close, stringResource(R.string.remove)) }
                }
                WeekdayChips(p.weekday) { weekly[i] = p.copy(weekday = it) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TimeButton(stringResource(R.string.from), p.start,
                        { weekly[i] = p.copy(start = it, duration = durationBetween(it, (p.start + p.duration) % MINUTES_PER_DAY)) })
                    TimeButton(stringResource(R.string.to), (p.start + p.duration) % MINUTES_PER_DAY,
                        { weekly[i] = p.copy(duration = durationBetween(p.start, it)) })
                }
            }
        }
        OutlinedButton(onClick = { weekly += ShiftPattern(weekly.lastOrNull()?.weekday?.plus(1)?.rem(7) ?: 0, 9 * 60, 8 * 60) }) {
            Text(stringResource(R.string.add_weekly_shift))
        }
    }
    if (confirmDelete && existing != null) ConfirmDialog(stringResource(R.string.delete_job_question, existing.name),
        stringResource(R.string.delete), onConfirm = { repo.deleteJob(existing.uid); close() },
        onDismiss = { confirmDelete = false })
}

// ---- courses ----

/** A course and its class times (the timetable). */
@Composable
fun CourseEditor(repo: Repository, uid: String?, close: () -> Unit) {
    val existing = remember(uid) { uid?.let(repo::course) }
    val used = remember { repo.courses().map { it.color }.toSet() }
    var name by remember { mutableStateOf(existing?.name.orEmpty()) }
    var teacher by remember { mutableStateOf(existing?.teacher.orEmpty()) }
    var room by remember { mutableStateOf(existing?.room.orEmpty()) }
    var color by remember { mutableStateOf(existing?.color ?: COURSE_COLORS.firstOrNull { it !in used } ?: COURSE_COLORS[0]) }
    val slots = remember { mutableStateListOf<ClassSlot>().apply { existing?.let { addAll(it.slots) } } }
    var confirmDelete by remember { mutableStateOf(false) }

    EditorSheet(stringResource(if (existing == null) R.string.new_course else R.string.edit_course), close,
        canSave = name.isNotBlank() && slots.all { it.end > it.start },
        onSave = {
            val base = existing ?: Course(Codec.newUid(), "")
            repo.saveCourse(base.copy(name = name, teacher = teacher, room = room, color = color, slots = slots.toList()))
            close()
        },
        onDelete = existing?.let { { confirmDelete = true } }) {
        OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.course_name)) })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(teacher, { teacher = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.teacher)) })
            OutlinedTextField(room, { room = it }, Modifier.weight(1f), singleLine = true,
                label = { Text(stringResource(R.string.room)) })
        }
        ColorPicker(color) { color = it }
        SectionTitle(stringResource(R.string.class_times))
        if (existing?.externalId != null) Hint(stringResource(R.string.course_from_register))
        for ((i, s) in slots.withIndex()) {
            Column(Modifier.fillMaxWidth().animateContentSize()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(weekdayName(s.weekday, TextStyle.FULL), Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    IconButton(onClick = { slots.removeAt(i) }) { Icon(Icons.Filled.Close, stringResource(R.string.remove)) }
                }
                WeekdayChips(s.weekday) { slots[i] = s.copy(weekday = it) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TimeButton(stringResource(R.string.from), s.start, { slots[i] = s.copy(start = it, end = maxOf(s.end, it + 60).coerceAtMost(MINUTES_PER_DAY)) })
                    TimeButton(stringResource(R.string.to), s.end, { slots[i] = s.copy(end = it) })
                }
                OutlinedTextField(s.room, { slots[i] = s.copy(room = it) }, Modifier.fillMaxWidth(), singleLine = true,
                    placeholder = { Text(stringResource(R.string.room_if_different)) })
            }
        }
        OutlinedButton(onClick = {
            val last = slots.lastOrNull()
            slots += if (last == null) ClassSlot(0, 8 * 60, 9 * 60) else ClassSlot((last.weekday + 1) % 7, last.start, last.end)
        }) { Text(stringResource(R.string.add_class_time)) }
    }
    if (confirmDelete && existing != null) ConfirmDialog(stringResource(R.string.delete_course_question, existing.name),
        stringResource(R.string.delete), onConfirm = { repo.deleteCourse(existing.uid); close() },
        onDismiss = { confirmDelete = false })
}

fun plainNumber(value: Double): String = if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
