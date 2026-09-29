package io.github.quezka.quire.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
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
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.monday
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.time.temporal.ChronoUnit
import java.util.Locale

private const val WEEKS = 4_000
private const val THIS_WEEK = WEEKS / 2

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WeekScreen(repo: Repository, version: Int, openTask: (String) -> Unit) {
    val today = repo.today()
    val thisMonday = today.monday()
    val pager = rememberPagerState(initialPage = THIS_WEEK) { WEEKS }
    val scope = rememberCoroutineScope()
    fun mondayOf(page: Int): LocalDate = thisMonday.plusWeeks((page - THIS_WEEK).toLong())
    val monday = mondayOf(pager.currentPage)
    var editing by remember { mutableStateOf<AgendaItem?>(null) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = {
                AnimatedContent(monday, transitionSpec = {
                    val dir = if (targetState > initialState) 1 else -1
                    (slideInHorizontally { it / 4 * dir } + fadeIn(tween(Motion.MEDIUM)))
                        .togetherWith(slideOutHorizontally { -it / 4 * dir } + fadeOut(tween(Motion.SHORT)))
                }, label = "week") { shown -> Text(weekTitle(shown, thisMonday), maxLines = 1) }
            },
            actions = {
                IconButton(onClick = { scope.launch { pager.animateScrollToPage(pager.currentPage - 1) } }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, stringResource(R.string.previous_week))
                }
                AnimatedVisibility(monday != thisMonday, enter = scaleIn() + fadeIn(), exit = scaleOut() + fadeOut()) {
                    IconButton(onClick = { scope.launch { pager.animateScrollToPage(THIS_WEEK) } }) {
                        Icon(Icons.Filled.Today, stringResource(R.string.this_week))
                    }
                }
                IconButton(onClick = { scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } }) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, stringResource(R.string.next_week))
                }
            },
        )
        HorizontalPager(pager, Modifier.fillMaxSize(), beyondViewportPageCount = 1, key = { it }) { page ->
            WeekPage(repo, version, mondayOf(page), today, openTask) { editing = it }
        }
    }
    AgendaEditors(repo, editing, null, editing?.day ?: today) { editing = null }
}

private fun weekTitle(monday: LocalDate, thisMonday: LocalDate): String {
    val sunday = monday.plusDays(6)
    val locale = Locale.getDefault()
    val range = if (monday.month == sunday.month)
        "${monday.dayOfMonth}–${sunday.dayOfMonth} ${sunday.format(DateTimeFormatter.ofPattern("MMM", locale))}"
    else "${monday.format(DateTimeFormatter.ofPattern("d MMM", locale))} – ${sunday.format(DateTimeFormatter.ofPattern("d MMM", locale))}"
    return if (monday.year != thisMonday.year) "$range ${sunday.year}" else range
}

@Composable
private fun WeekPage(repo: Repository, version: Int, monday: LocalDate, today: LocalDate,
                     openTask: (String) -> Unit, onItem: (AgendaItem) -> Unit) {
    val days = remember(version, monday) { repo.week(monday) }
    val due = remember(version, monday) { repo.tasksDue(monday, monday.plusDays(6)).groupBy { it.due } }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items(days, key = { it.first.toString() }) { (day, items) ->
            val tasks = due[day].orEmpty()
            val isToday = day == today
            Card(Modifier.animateItem(), shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = if (isToday)
                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.45f)
                else MaterialTheme.colorScheme.surfaceContainerLow)) {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(34.dp).background(
                            if (isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                            CircleShape), contentAlignment = Alignment.Center) {
                            Text(day.dayOfMonth.toString(), fontWeight = FontWeight.Bold,
                                color = if (isToday) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface)
                        }
                        Spacer(Modifier.width(10.dp))
                        Text(day.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.getDefault())
                            .replaceFirstChar { it.titlecase(Locale.getDefault()) },
                            fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        if (isToday) Text(stringResource(R.string.today), color = MaterialTheme.colorScheme.primary,
                            style = MaterialTheme.typography.labelMedium)
                    }
                    if (items.isEmpty() && tasks.isEmpty()) Hint(stringResource(R.string.free_day))
                    for (item in items) WeekItem(item) { onItem(item) }
                    for (t in tasks) Row(Modifier.fillMaxWidth().clickable { openTask(t.uid) }.padding(vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(if (t.done) "✓" else "○", color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.width(20.dp))
                        Text(t.title, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            textDecoration = if (t.done) TextDecoration.LineThrough else null,
                            style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun WeekItem(item: AgendaItem, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(parseColor(item.color), CircleShape))
        Spacer(Modifier.width(10.dp))
        Text(span(item.start, item.end), style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(92.dp))
        Text(item.title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f))
        if (item.room.isNotBlank()) Text(item.room, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
