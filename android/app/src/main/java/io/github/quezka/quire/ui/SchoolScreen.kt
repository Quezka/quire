package io.github.quezka.quire.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.Container
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.Absence
import io.github.quezka.quire.domain.AbsenceKind
import io.github.quezka.quire.domain.PASS_MARK
import io.github.quezka.quire.domain.School
import io.github.quezka.quire.domain.average
import io.github.quezka.quire.domain.formatMark
import io.github.quezka.quire.domain.neededGrade
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val AMBER = Color(0xFFF5A524)

@Composable
fun SchoolScreen(container: Container, version: Int, back: () -> Unit) {
    val school = container.school
    val state by container.schoolState.collectAsState()
    var refresh by remember { mutableIntStateOf(0) }
    val status = remember(version, refresh, state) { school.status() }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    fun syncNow() = scope.launch {
        runCatching { withContext(Dispatchers.IO) { container.syncSchool() } }
        refresh++
    }

    Column(Modifier.fillMaxSize()) {
        PageBar(stringResource(R.string.nav_school), back) {
            if (status.connected) IconButton(onClick = { syncNow() }, enabled = !state.running) {
                val turn by animateFloatAsState(if (state.running) 360f else 0f, tween(900), label = "sync")
                Icon(Icons.Filled.Sync, stringResource(R.string.sync_now), Modifier.rotate(turn))
            }
        }
        if (state.running) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.problem?.let {
            Text(registerMessage(context, it), color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp))
        }
        AnimatedContent(status.connected, label = "connected") { connected ->
            if (!connected) ConnectSchool(container) { refresh++; syncNow() }
            else SchoolTabs(container, version + refresh)
        }
    }
}

/** The register speaks English (like the desktop's core); show it in the phone's language. */
fun registerMessage(context: android.content.Context, message: String): String = when {
    message.contains("didn't accept that username") -> context.getString(R.string.err_register_login)
    message.contains("Couldn't reach Classeviva") -> context.getString(R.string.err_register_offline)
    message.contains("session was refused") || message.contains("again") -> context.getString(R.string.err_register_session)
    else -> message
}

@Composable
private fun ConnectSchool(container: Container, connected: () -> Unit) {
    var user by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Panel(stringResource(R.string.connect_classeviva)) {
            Hint(stringResource(R.string.connect_classeviva_help))
            OutlinedTextField(user, { user = it }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text(stringResource(R.string.register_username)) })
            OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text(stringResource(R.string.password)) }, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(enabled = !busy && user.isNotBlank() && password.isNotEmpty(), onClick = {
                busy = true; error = null
                scope.launch {
                    val result = runCatching { withContext(Dispatchers.IO) { container.school.connect(user, password) } }
                    busy = false
                    result.exceptionOrNull()?.let { error = registerMessage(context, it.message.orEmpty()) } ?: connected()
                }
            }) { Text(stringResource(if (busy) R.string.connecting else R.string.connect)) }
            Hint(stringResource(R.string.school_privacy))
        }
    }
}

@Composable
private fun SchoolTabs(container: Container, version: Int) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val data = remember(version) { container.school.data() }
    val courses = remember(version) { container.repository.courses() }
    val titles = listOf(R.string.school_overview, R.string.grades, R.string.absences, R.string.topics, R.string.notices)
    Column(Modifier.fillMaxSize()) {
        @OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
        PrimaryScrollableTabRow(tab, edgePadding = 12.dp) {
            titles.forEachIndexed { i, t ->
                Tab(tab == i, { tab = i }, text = { Text(stringResource(t)) })
            }
        }
        AnimatedContent(tab, transitionSpec = { with(Motion) { push(targetState > initialState) } }, label = "school-tab") { shown ->
            when (shown) {
                0 -> Overview(container, data)
                1 -> Grades(data.grades)
                2 -> Absences(container, data, courses)
                3 -> Topics(data.lessons)
                else -> Notices(container, data.notices)
            }
        }
    }
}

@Composable
private fun markColor(value: Double?): Color = when {
    value == null -> MaterialTheme.colorScheme.onSurfaceVariant
    value < PASS_MARK -> MaterialTheme.colorScheme.error
    value < PASS_MARK + 0.5 -> AMBER
    else -> MaterialTheme.colorScheme.tertiary
}

@Composable
private fun Overview(container: Container, data: io.github.quezka.quire.domain.RegisterData) {
    val bySubject = data.grades.groupBy { it.subject }.map { (s, g) -> Triple(s, g, average(g)) }.sortedBy { it.first }
    val overall = average(data.grades)
    val context = LocalContext.current
    var detail by remember { mutableStateOf<String?>(null) }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item(key = "tiles") {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatTile(stringResource(R.string.average), overall?.let(::formatMark) ?: "—",
                    pluralStringResource(R.plurals.grades_count, data.grades.count { it.counts }, data.grades.count { it.counts }),
                    Modifier.weight(1f), markColor(overall))
                val below = bySubject.count { (it.third ?: 10.0) < PASS_MARK }
                StatTile(stringResource(R.string.below_six), below.toString(), "", Modifier.weight(1f),
                    if (below > 0) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.tertiary)
            }
        }
        data.lastSync?.let { item(key = "last") { Hint(context.getString(R.string.last_synced, it.replace('T', ' ').take(16))) } }
        if (bySubject.isEmpty()) item(key = "none") { Hint(stringResource(R.string.no_grades)) }
        items(bySubject, key = { it.first }) { (subject, grades, avg) ->
            Row(Modifier.fillMaxWidth().animateItem().clickable { detail = subject }.padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(subject, fontWeight = FontWeight.SemiBold)
                    Hint(grades.sortedByDescending { it.day }.take(6).joinToString("  ") { it.display })
                }
                MarkBadge(avg?.let(::formatMark) ?: "—", markColor(avg))
            }
        }
    }
    detail?.let { subject ->
        val values = data.grades.filter { it.subject == subject && it.counts }.mapNotNull { it.value }
        AlertDialog(onDismissRequest = { detail = null }, title = { Text(subject) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (target in listOf(6.0, 7.0, 8.0)) {
                        val need = neededGrade(values, target)
                        Text(when {
                            need <= 1 -> context.getString(R.string.target_safe, formatMark(target))
                            need > 10 -> context.getString(R.string.target_out_of_reach, formatMark(target))
                            else -> context.getString(R.string.target_needs, formatMark(target), formatMark(need))
                        })
                    }
                }
            },
            confirmButton = { TextButton(onClick = { detail = null }) { Text(stringResource(R.string.ok)) } })
    }
}

@Composable
private fun MarkBadge(text: String, color: Color) {
    Box(Modifier.widthIn(min = 48.dp).background(color.copy(alpha = 0.15f), RoundedCornerShape(10.dp))
        .padding(horizontal = 10.dp, vertical = 6.dp), contentAlignment = Alignment.Center) {
        Text(text, color = color, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun Grades(grades: List<io.github.quezka.quire.domain.Grade>) {
    val context = LocalContext.current
    val today = java.time.LocalDate.now()
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (grades.isEmpty()) item { Hint(stringResource(R.string.no_grades)) }
        items(grades.sortedByDescending { it.day }, key = { it.id }) { g ->
            Row(Modifier.fillMaxWidth().animateItem().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                MarkBadge(g.display.ifEmpty { "—" }, if (g.cancelled) MaterialTheme.colorScheme.onSurfaceVariant else markColor(g.value))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(g.subject, fontWeight = FontWeight.SemiBold)
                    Hint(listOf(relativeDate(context, g.day, today), g.component, g.notes)
                        .filter { it.isNotBlank() }.joinToString(" · "))
                }
            }
        }
    }
}

@Composable
private fun Absences(container: Container, data: io.github.quezka.quire.domain.RegisterData,
                     courses: List<io.github.quezka.quire.domain.Course>) {
    val summary = School.absenceSummary(data, courses)
    val perDay = School.hoursPerWeekday(courses)
    val context = LocalContext.current
    val today = java.time.LocalDate.now()
    var editing by remember { mutableStateOf<Absence?>(null) }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item(key = "tiles") {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatTile(stringResource(R.string.hours_missed), summary.hoursMissed.toString(),
                    if (summary.share == null) "" else context.getString(R.string.of_about_allowed, summary.limitHours),
                    Modifier.weight(1f))
                StatTile(stringResource(R.string.days_absent), summary.absentDays.toString(),
                    if (summary.unjustified > 0) context.getString(R.string.not_justified_count, summary.unjustified) else "",
                    Modifier.weight(1f))
            }
        }
        item(key = "limit") {
            Panel(stringResource(R.string.towards_limit)) {
                val share = summary.share
                if (share == null) Hint(stringResource(R.string.add_timetable_for_limit))
                else {
                    val used = if (summary.limitHours > 0) summary.hoursMissed.toFloat() / summary.limitHours else 1f
                    val shown by animateFloatAsState(used.coerceIn(0f, 1f), tween(700), label = "limit")
                    LinearProgressIndicator({ shown }, Modifier.fillMaxWidth().height(8.dp),
                        color = when { used >= 0.8f -> MaterialTheme.colorScheme.error; used >= 0.5f -> AMBER
                            else -> MaterialTheme.colorScheme.tertiary })
                    Hint(context.getString(R.string.limit_text, summary.hoursMissed, summary.limitHours,
                        "%.1f".format(share * 100), summary.hoursLeft))
                }
            }
        }
        if (data.absences.isEmpty()) item(key = "none") { Hint(stringResource(R.string.no_absences)) }
        if (data.absences.any { it.needsHour }) item(key = "hint") { Hint(stringResource(R.string.tap_to_enter_hour)) }
        items(data.absences.sortedByDescending { it.day }, key = { it.id }) { a ->
            Row(Modifier.fillMaxWidth().animateItem().clickable(enabled = a.needsHour) { editing = a }
                .padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).background(if (a.justified) MaterialTheme.colorScheme.tertiary
                    else MaterialTheme.colorScheme.error, RoundedCornerShape(5.dp)))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f).animateContentSize()) {
                    Text(absenceTitle(context, a), fontWeight = FontWeight.SemiBold,
                        color = if (a.needsHour && a.knownHour == null) AMBER else MaterialTheme.colorScheme.onSurface)
                    val missed = a.hoursMissed(perDay[a.day.dayOfWeek.value - 1] ?: 0)
                    Hint(listOfNotNull(relativeDate(context, a.day, today),
                        if (missed > 0) context.resources.getQuantityString(R.plurals.hours, missed, missed) else null,
                        if (a.hourIsYours) context.getString(R.string.hour_entered_by_you) else null,
                        context.getString(if (a.justified) R.string.justified else R.string.not_justified),
                        a.reason.ifBlank { null }).joinToString(" · "))
                }
            }
        }
    }
    editing?.let { a -> AbsenceHourDialog(a, save = { container.school.setAbsenceHour(a.id, it); editing = null },
        dismiss = { editing = null }) }
}

fun absenceTitle(context: android.content.Context, a: Absence): String = when (a.kind) {
    AbsenceKind.ABSENT -> context.getString(R.string.absent)
    AbsenceKind.SHORT_LATE -> context.getString(R.string.few_minutes_late)
    AbsenceKind.LATE -> a.knownHour?.let { context.getString(R.string.late_entry_hour, it) }
        ?: context.getString(R.string.late_entry_no_hour)
    AbsenceKind.EARLY_EXIT -> a.knownHour?.let { context.getString(R.string.left_early_hour, it) }
        ?: context.getString(R.string.left_early_no_hour)
}

@Composable
private fun AbsenceHourDialog(a: Absence, save: (Int?) -> Unit, dismiss: () -> Unit) {
    val late = a.kind == AbsenceKind.LATE
    var hour by remember { mutableIntStateOf(a.knownHour ?: if (late) 2 else 5) }
    AlertDialog(onDismissRequest = dismiss, title = { Text(stringResource(R.string.lesson_hour)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(if (late) R.string.hour_came_in_question else R.string.hour_left_question))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = { if (hour > 1) hour-- }) { Text("−") }
                    AnimatedNumber(stringResource(R.string.nth_hour, hour), MaterialTheme.colorScheme.onSurface)
                    OutlinedButton(onClick = { if (hour < io.github.quezka.quire.domain.MAX_LESSON_HOUR) hour++ }) { Text("+") }
                }
            }
        },
        confirmButton = { TextButton(onClick = { save(hour) }) { Text(stringResource(R.string.save)) } },
        dismissButton = {
            Row {
                if (a.hourIsYours) TextButton(onClick = { save(null) }) { Text(stringResource(R.string.forget)) }
                TextButton(onClick = dismiss) { Text(stringResource(R.string.cancel)) }
            }
        })
}

@Composable
private fun Topics(lessons: List<io.github.quezka.quire.domain.Lesson>) {
    val context = LocalContext.current
    val today = java.time.LocalDate.now()
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (lessons.isEmpty()) item { Hint(stringResource(R.string.no_topics)) }
        val byDay = lessons.filter { it.topic.isNotBlank() }.sortedWith(compareByDescending<io.github.quezka.quire.domain.Lesson> { it.day }.thenBy { it.hour })
            .groupBy { it.day }
        for ((day, list) in byDay) {
            item(key = "day-$day") { SectionTitle(relativeDate(context, day, today)) }
            items(list, key = { it.id }) { l ->
                Column(Modifier.animateItem().padding(vertical = 4.dp)) {
                    Text(l.subject + if (l.hour > 0) " · " + context.getString(R.string.nth_hour, l.hour) else "",
                        fontWeight = FontWeight.SemiBold)
                    Text(l.topic, style = MaterialTheme.typography.bodyMedium)
                    if (l.teacher.isNotBlank()) Hint(l.teacher)
                }
            }
        }
    }
}

@Composable
private fun Notices(container: Container, notices: List<io.github.quezka.quire.domain.Notice>) {
    val context = LocalContext.current
    val today = java.time.LocalDate.now()
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (notices.isEmpty()) item { Hint(stringResource(R.string.no_notices)) }
        items(notices.sortedByDescending { it.published }, key = { it.id }) { n ->
            Row(Modifier.fillMaxWidth().animateItem().clickable { container.school.markNoticeRead(n.id) }
                .padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                val dot by animateFloatAsState(if (n.read) 0f else 1f, tween(Motion.MEDIUM), label = "unread")
                Box(Modifier.size(8.dp).background(MaterialTheme.colorScheme.primary.copy(alpha = dot), RoundedCornerShape(4.dp)))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(n.title, fontWeight = if (n.read) FontWeight.Normal else FontWeight.SemiBold)
                    Hint(listOf(relativeDate(context, n.published, today), n.category).filter { it.isNotBlank() }.joinToString(" · "))
                }
            }
        }
    }
}
