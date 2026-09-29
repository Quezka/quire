package io.github.quezka.quire.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
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
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.Today
import androidx.compose.material.icons.filled.Work
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.TaskKind
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.absoluteValue

/** Pages either side of today in the day pager (about 27 years). */
private const val DAYS = 20_000
private const val TODAY_PAGE = DAYS / 2

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(repo: Repository, version: Int, openTask: (String) -> Unit, newTask: (LocalDate) -> Unit) {
    val today = repo.today()
    val pager = rememberPagerState(initialPage = TODAY_PAGE) { DAYS }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    fun dayOf(page: Int): LocalDate = today.plusDays((page - TODAY_PAGE).toLong())
    fun pageOf(day: LocalDate) = TODAY_PAGE + ChronoUnit.DAYS.between(today, day).toInt()
    val day = dayOf(pager.currentPage)
    var editing by remember { mutableStateOf<AgendaItem?>(null) }
    var adding by remember { mutableStateOf<ItemKind?>(null) }
    var menu by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            TopAppBar(
                title = {
                    // The date slides the same way as the page.
                    AnimatedContent(day, transitionSpec = {
                        val dir = if (targetState > initialState) 1 else -1
                        (slideInHorizontally { it / 4 * dir } + fadeIn(tween(Motion.MEDIUM)))
                            .togetherWith(slideOutHorizontally { -it / 4 * dir } + fadeOut(tween(Motion.SHORT)))
                    }, label = "date") { shown ->
                        Column {
                            Text(longDate(shown, today), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (shown != today) Text(relativeDate(context, shown, today),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { scope.launch { pager.animateScrollToPage(pager.currentPage - 1) } }) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, stringResource(R.string.previous_day))
                    }
                    AnimatedVisibility(day != today, enter = scaleIn() + fadeIn(), exit = scaleOut() + fadeOut()) {
                        IconButton(onClick = { scope.launch { pager.animateScrollToPage(pageOf(today)) } }) {
                            Icon(Icons.Filled.Today, stringResource(R.string.back_to_today))
                        }
                    }
                    IconButton(onClick = { scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } }) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, stringResource(R.string.next_day))
                    }
                },
            )
            HorizontalPager(pager, Modifier.fillMaxSize(), beyondViewportPageCount = 1,
                key = { it }) { page ->
                // Neighbouring days fade and shrink a little as they slide in.
                val offset = ((pager.currentPage - page) + pager.currentPageOffsetFraction).absoluteValue.coerceIn(0f, 1f)
                Box(Modifier.graphicsLayer {
                    alpha = 1f - offset * 0.35f
                    val scale = 1f - offset * 0.04f
                    scaleX = scale; scaleY = scale
                }) {
                    DayPage(repo, version, dayOf(page), today, openTask, onItem = { editing = it })
                }
            }
        }
        FloatingActionButton(onClick = { menu = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            val turn by animateFloatAsState(if (menu) 45f else 0f, Motion.bouncy(), label = "fab")
            Icon(Icons.Filled.Add, stringResource(R.string.add), Modifier.graphicsLayer { rotationZ = turn })
            DropdownMenu(menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text(stringResource(R.string.new_task)) },
                    leadingIcon = { Icon(Icons.Filled.CheckCircle, null) },
                    onClick = { menu = false; newTask(day) })
                DropdownMenuItem(text = { Text(stringResource(R.string.new_event)) },
                    leadingIcon = { Icon(Icons.Filled.Event, null) },
                    onClick = { menu = false; adding = ItemKind.EVENT })
                DropdownMenuItem(text = { Text(stringResource(R.string.new_shift)) },
                    leadingIcon = { Icon(Icons.Filled.Work, null) },
                    onClick = { menu = false; adding = ItemKind.SHIFT })
            }
        }
    }

    AgendaEditors(repo, editing, adding, day) { editing = null; adding = null }
}

/** One day: schedule, tasks, quick add and the day note. */
@Composable
private fun DayPage(repo: Repository, version: Int, day: LocalDate, today: LocalDate,
                    openTask: (String) -> Unit, onItem: (AgendaItem) -> Unit) {
    val agenda = remember(version, day) { repo.day(day) }
    val courses = remember(version) { repo.courseIndex() }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 96.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item(key = "schedule") { SectionTitle(stringResource(R.string.schedule)) }
        if (agenda.items.isEmpty()) item(key = "no-items") { Hint(stringResource(R.string.nothing_scheduled)) }
        items(agenda.items, key = { "${it.kind}-${it.refUid}-${it.start}-${it.continues}" }) {
            Box(Modifier.animateItem()) { AgendaRow(it, onClick = { onItem(it) }) }
        }

        item(key = "todo") { SectionTitle(stringResource(R.string.to_do)) }
        if (agenda.tasks.isEmpty()) item(key = "no-tasks") { Hint(stringResource(R.string.nothing_due)) }
        items(agenda.tasks, key = { it.uid }) { task ->
            Box(Modifier.animateItem()) {
                TaskRow(task, courses[task.courseUid]?.name, today,
                    onCheck = { repo.setDone(task.uid, it) }, onOpen = { openTask(task.uid) })
            }
        }
        item(key = "quick-add") { QuickAdd(onAdd = { title -> repo.saveTask(Task(Codec.newUid(), title, due = day)) }) }

        item(key = "note-title") { SectionTitle(stringResource(R.string.day_note)) }
        item(key = "note-$day") { DayNote(repo, day, agenda.journal) }
    }
}

@Composable
fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(top = 12.dp, bottom = 2.dp))
}

@Composable
fun Hint(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun AgendaRow(item: AgendaItem, onClick: (() -> Unit)? = null) {
    val kind = stringResource(when (item.kind) {
        ItemKind.CLASS -> R.string.kind_class
        ItemKind.EVENT -> R.string.kind_event
        ItemKind.SHIFT -> R.string.kind_shift
    })
    val extra = listOf(item.room, item.teacher, item.details.lineSequence().firstOrNull().orEmpty())
        .filter { it.isNotBlank() }
    val source = remember { MutableInteractionSource() }
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.pressScale(source).then(
            if (onClick != null) Modifier.clickable(source, null, onClick = onClick) else Modifier),
    ) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(4.dp).height(40.dp)
                .background(parseColor(item.color), RoundedCornerShape(2.dp)))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(item.title, fontWeight = FontWeight.SemiBold, maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
                val meta = buildList {
                    add(span(item.start, item.end)); add(kind); addAll(extra)
                    if (item.continues) add(stringResource(R.string.continues_from_yesterday))
                }
                Text(meta.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2,
                    overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
fun TaskRow(task: Task, course: String?, today: LocalDate, onCheck: (Boolean) -> Unit, onOpen: () -> Unit) {
    val context = LocalContext.current
    // Ticking off fades the title rather than snapping.
    val faded by animateFloatAsState(if (task.done) 0.55f else 1f, tween(Motion.MEDIUM), label = "done")
    val color by animateColorAsState(
        if (task.isOverdue(today)) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
        tween(Motion.MEDIUM), label = "color")
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onOpen).padding(vertical = 2.dp)
            .graphicsLayer { alpha = faded },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = task.done, onCheckedChange = onCheck)
        Column(Modifier.weight(1f)) {
            Text(task.title, maxLines = 2, overflow = TextOverflow.Ellipsis,
                textDecoration = if (task.done) TextDecoration.LineThrough else null, color = color)
            val due = task.due
            val meta = listOfNotNull(
                course,
                stringResource(kindLabel(task.kind)).takeIf { task.kind != TaskKind.TASK },
                due?.let {
                    if (task.isOverdue(today)) context.getString(R.string.was_due, relativeDateInline(context, it, today))
                    else relativeDate(context, it, today)
                },
            )
            if (meta.isNotEmpty()) Text(meta.joinToString(" · "), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun QuickAdd(onAdd: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(text, { text = it }, Modifier.weight(1f),
            placeholder = { Text(stringResource(R.string.quick_add_hint)) }, singleLine = true,
            keyboardActions = KeyboardActions(onDone = {
                if (text.isNotBlank()) { onAdd(text); text = "" }
            }),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done))
        IconButton(onClick = { if (text.isNotBlank()) { onAdd(text); text = "" } }) {
            Icon(Icons.Filled.Add, stringResource(R.string.add))
        }
    }
}

/** Saved shortly after typing stops, and when leaving the day. Changes that arrive by sync
 *  replace the text unless it's being edited (then the edit wins, as on the desktop). */
@Composable
private fun DayNote(repo: Repository, day: LocalDate, stored: String) {
    var text by remember(day) { mutableStateOf(stored) }
    var dirty by remember(day) { mutableStateOf(false) }
    LaunchedEffect(stored) { if (!dirty) text = stored }
    LaunchedEffect(text, dirty) {
        if (dirty) {
            delay(800)
            repo.saveJournal(day, text)
            dirty = false
        }
    }
    DisposableEffect(day) {
        onDispose { if (dirty) repo.saveJournal(day, text) }
    }
    OutlinedTextField(text, { text = it; dirty = true }, Modifier.fillMaxWidth().heightIn(min = 120.dp),
        placeholder = { Text(stringResource(R.string.day_note_hint)) })
}
