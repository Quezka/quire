package io.github.quezka.quire.ui

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Agenda
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.MINUTES_PER_DAY
import io.github.quezka.quire.domain.Work
import io.github.quezka.quire.domain.pay
import io.github.quezka.quire.domain.paidMinutes

/** Jobs, shifts coming up, and what this week and month pay. */
@Composable
fun WorkScreen(repo: Repository, version: Int, back: () -> Unit) {
    val today = repo.today()
    var month by rememberSaveable { mutableStateOf(false) }
    val jobs = remember(version) { repo.jobs() }
    val summary = remember(version, month) { if (month) repo.workMonth() else repo.workWeek() }
    val upcoming = remember(version) {
        val now = repo.now()
        val minute = now.hour * 60 + now.minute
        Agenda.shifts(jobs, repo.shifts(), today.minusDays(1), today.plusDays(28))
            .filter { java.time.temporal.ChronoUnit.DAYS.between(today, it.day) * MINUTES_PER_DAY + it.end > minute }
            .take(12)
    }
    var editingJob by remember { mutableStateOf<String?>(null) }
    var newJob by remember { mutableStateOf(false) }
    var newShift by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<AgendaItem?>(null) }
    val context = LocalContext.current

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            PageBar(stringResource(R.string.nav_work), back)
            LazyColumn(contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 96.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item(key = "period") {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        SegmentedButton(!month, { month = false }, SegmentedButtonDefaults.itemShape(0, 2)) {
                            Text(stringResource(R.string.this_week)) }
                        SegmentedButton(month, { month = true }, SegmentedButtonDefaults.itemShape(1, 2)) {
                            Text(stringResource(R.string.this_month)) }
                    }
                }
                item(key = "tiles") {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        StatTile(stringResource(R.string.hours), hoursText(summary.minutes),
                            context.resources.getQuantityString(R.plurals.shifts, summary.shifts, summary.shifts),
                            Modifier.weight(1f))
                        StatTile(stringResource(R.string.take_home), summary.net?.let(::money) ?: "—",
                            summary.pay?.let { context.getString(R.string.before_deductions, money(it)) } ?: "",
                            Modifier.weight(1f))
                    }
                }
                if (summary.totals.size > 1) items(summary.totals, key = { "total-" + (it.job?.uid ?: "") }) { t ->
                    Row(Modifier.animateItem(), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp).background(parseColor(t.job?.color ?: "#0090ff"), CircleShape))
                        Spacer(Modifier.width(10.dp))
                        Text(t.job?.name.orEmpty(), Modifier.weight(1f))
                        Text(hoursText(t.minutes) + (t.net?.let { " · " + money(it) } ?: ""),
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                item(key = "upcoming") { SectionTitle(stringResource(R.string.upcoming_shifts)) }
                if (upcoming.isEmpty()) item(key = "no-upcoming") { Hint(stringResource(R.string.no_upcoming_shifts)) }
                items(upcoming, key = { "${it.uid ?: it.jobUid}-${it.day}-${it.start}" }) { s ->
                    val job = jobs.firstOrNull { it.uid == s.jobUid }
                    val item = AgendaItem(ItemKind.SHIFT, s.uid ?: s.jobUid, s.day, s.start,
                        minOf(s.end, MINUTES_PER_DAY), job?.name ?: "", job?.color ?: "#0090ff",
                        details = listOfNotNull(relativeDate(context, s.day, today), hoursText(s.paidMinutes),
                            s.pay(job?.hourlyRate)?.let(::money)).joinToString(" · "),
                        weekly = s.uid == null)
                    Box(Modifier.animateItem()) { AgendaRow(item) { editing = item } }
                }
                item(key = "jobs") { SectionTitle(stringResource(R.string.jobs)) }
                if (jobs.isEmpty()) item(key = "no-jobs") { Hint(stringResource(R.string.no_jobs)) }
                items(jobs, key = { it.uid }) { job ->
                    val weekly = Work.activeSchedule(job, today)
                    Row(Modifier.fillMaxWidth().animateItem().clickable { editingJob = job.uid }.padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(12.dp).background(parseColor(job.color), CircleShape))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(job.name, fontWeight = FontWeight.SemiBold)
                            val meta = listOfNotNull(
                                job.hourlyRate?.let { context.getString(R.string.per_hour, money(it)) },
                                if (weekly.isEmpty()) null else weekly.joinToString(", ") {
                                    "${weekdayName(it.weekday)} ${span(it.start, (it.start + it.duration) % MINUTES_PER_DAY)}"
                                })
                            if (meta.isNotEmpty()) Hint(meta.joinToString(" · "))
                        }
                    }
                }
                item(key = "add-job") {
                    OutlinedButton(onClick = { newJob = true }) { Text(stringResource(R.string.new_job)) }
                }
            }
        }
        FloatingActionButton(onClick = { newShift = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            Icon(Icons.Filled.Add, stringResource(R.string.new_shift))
        }
    }
    when {
        newJob -> JobEditor(repo, null) { newJob = false }
        editingJob != null -> JobEditor(repo, editingJob) { editingJob = null }
        else -> AgendaEditors(repo, editing, if (newShift) ItemKind.SHIFT else null, editing?.day ?: today) {
            editing = null; newShift = false
        }
    }
}
