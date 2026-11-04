package io.github.quezka.quire.widget

import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.ColorFilter
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.LocalSize
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.appWidgetBackground
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.lazy.LazyColumn
import androidx.glance.appwidget.lazy.items
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.material3.ColorProviders
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import io.github.quezka.quire.MainActivity
import io.github.quezka.quire.R
import io.github.quezka.quire.container
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.WidgetAgenda
import io.github.quezka.quire.domain.WidgetDay
import io.github.quezka.quire.domain.WidgetEntry
import io.github.quezka.quire.ui.Dark
import io.github.quezka.quire.ui.Light
import io.github.quezka.quire.ui.kindLabel
import io.github.quezka.quire.ui.minutes
import io.github.quezka.quire.ui.parseColor
import io.github.quezka.quire.ui.relativeDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/** The home-screen agenda: what's coming up in the next days, tasks and timeline together. */
class AgendaWidget : GlanceAppWidget() {
    // Laid out again at the size it really has, so it can be dragged smaller or bigger.
    override val sizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val repo = context.container.repository
        val (now, days) = withContext(Dispatchers.IO) {
            repo.now() to WidgetAgenda.build(repo.now(), repo.courses(), repo.events(), repo.jobs(),
                repo.shifts(), repo.tasks(), repo.routines())
        }
        provideContent {
            // The system's Material You colours where there are any (Android 12), else Quire's own.
            GlanceTheme(if (Build.VERSION.SDK_INT >= 31) GlanceTheme.colors else QuireWidgetColors) {
                AgendaContent(context, now.toLocalDate(), days)
            }
        }
    }

    companion object {
        val scope = CoroutineScope(Dispatchers.Default)
        private var pending: Job? = null

        /** Redraw now (for a broadcast receiver that holds the process open meanwhile). */
        suspend fun refreshNow(context: Context) = AgendaWidget().updateAll(context.applicationContext)

        /** Redraw every placed widget; bursts of changes (a sync) collapse into one redraw. */
        fun refresh(context: Context) {
            val app = context.applicationContext
            pending?.cancel()
            pending = scope.launch {
                delay(400)
                AgendaWidget().updateAll(app)
            }
        }
    }
}

class AgendaWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = AgendaWidget()
}

internal val QuireWidgetColors = ColorProviders(light = Light, dark = Dark)

@Composable
internal fun AgendaContent(context: Context, today: LocalDate, days: List<WidgetDay>) {
    val colors = GlanceTheme.colors
    val compact = LocalSize.current.height < 150.dp  // a short widget gives its room to the agenda
    val corners = if (Build.VERSION.SDK_INT >= 31) GlanceModifier.cornerRadius(android.R.dimen.system_app_widget_background_radius)
        else GlanceModifier.cornerRadius(24.dp)
    Column(GlanceModifier.fillMaxSize().appWidgetBackground().background(colors.widgetBackground).then(corners)) {
        Row(GlanceModifier.fillMaxWidth().padding(start = 16.dp, end = 12.dp, top = if (compact) 6.dp else 14.dp, bottom = if (compact) 2.dp else 6.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Column(GlanceModifier.defaultWeight().clickable(openApp(context, 0))) {
                if (!compact) Text(today.format(DateTimeFormatter.ofPattern("EEEE", Locale.getDefault()))
                    .replaceFirstChar { it.titlecase(Locale.getDefault()) },
                    style = TextStyle(color = colors.primary, fontSize = 12.sp, fontWeight = FontWeight.Medium))
                Text(today.format(DateTimeFormatter.ofPattern("d MMMM", Locale.getDefault())),
                    maxLines = 1, style = TextStyle(color = colors.onSurface, fontSize = if (compact) 16.sp else 22.sp, fontWeight = FontWeight.Normal))
            }
            // A small tonal button, with Material's rounded square.
            Box(GlanceModifier.size(if (compact) 36.dp else 44.dp).background(colors.primaryContainer).cornerRadius(14.dp)
                .clickable(openApp(context, 2, newTask = true)), contentAlignment = Alignment.Center) {
                Image(ImageProvider(R.drawable.ic_widget_add), context.getString(R.string.add_task),
                    GlanceModifier.size(24.dp), colorFilter = ColorFilter.tint(colors.onPrimaryContainer))
            }
        }
        if (days.isEmpty()) {
            Box(GlanceModifier.fillMaxSize().clickable(openApp(context, 0)), contentAlignment = Alignment.Center) {
                Text(context.getString(R.string.widget_empty),
                    style = TextStyle(color = colors.onSurfaceVariant, fontSize = 14.sp))
            }
        } else {
            LazyColumn(GlanceModifier.fillMaxSize().padding(horizontal = 10.dp)) {
                for (day in days) {
                    item {
                        Text(relativeDate(context, day.day, today),
                            GlanceModifier.fillMaxWidth().padding(start = 8.dp, top = 10.dp, bottom = 4.dp),
                            style = TextStyle(color = colors.primary, fontSize = 12.sp, fontWeight = FontWeight.Medium))
                    }
                    items(day.entries) { entry ->
                        when (entry) {
                            is WidgetEntry.Timed -> TimedRow(context, entry)
                            is WidgetEntry.Due -> DueRow(context, entry, today)
                        }
                    }
                }
                item { Spacer(GlanceModifier.height(8.dp)) }
            }
        }
    }
}

@Composable
internal fun TimedRow(context: Context, entry: WidgetEntry.Timed) {
    val item = entry.item
    val tag = when (item.kind) {
        ItemKind.CLASS -> item.room
        ItemKind.EVENT, ItemKind.ROUTINE -> ""
        ItemKind.SHIFT -> context.getString(R.string.kind_shift)
    }
    val colors = GlanceTheme.colors
    RowCard {
        Row(GlanceModifier.fillMaxWidth().background(colors.surfaceVariant).cornerRadius(14.dp)
            .padding(horizontal = 10.dp, vertical = 8.dp).clickable(openApp(context, 0)),
            verticalAlignment = Alignment.CenterVertically) {
            Box(GlanceModifier.width(4.dp).height(32.dp).background(parseColor(item.color)).cornerRadius(2.dp)) {}
            Spacer(GlanceModifier.width(10.dp))
            Column(GlanceModifier.defaultWeight()) {
                Text(item.title, maxLines = 1, style = TextStyle(color = colors.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium))
                Text(listOf("${minutes(item.start)}–${minutes(item.end)}", tag).filter { it.isNotBlank() }.joinToString(" · "),
                    maxLines = 1, style = TextStyle(color = colors.onSurfaceVariant, fontSize = 12.sp))
            }
        }
    }
}

/** The gap between the rows of the list. */
@Composable
private fun RowCard(content: @Composable () -> Unit) {
    Box(GlanceModifier.fillMaxWidth().padding(vertical = 2.dp)) { content() }
}

@Composable
internal fun DueRow(context: Context, entry: WidgetEntry.Due, today: LocalDate) {
    val task = entry.task
    val colors = GlanceTheme.colors
    RowCard {
        Row(GlanceModifier.fillMaxWidth().background(colors.surfaceVariant).cornerRadius(14.dp)
            .padding(start = 4.dp, end = 10.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Box(GlanceModifier.size(36.dp).clickable(actionRunCallback<CompleteTask>(
                actionParametersOf(TaskUid to task.uid, TaskDone to !task.done))), contentAlignment = Alignment.Center) {
                Image(ImageProvider(if (task.done) R.drawable.ic_widget_check else R.drawable.ic_widget_circle),
                    context.getString(if (task.done) R.string.mark_not_done else R.string.mark_done),
                    GlanceModifier.size(22.dp),
                    colorFilter = ColorFilter.tint(if (task.done) colors.primary else colors.onSurfaceVariant))
            }
            Spacer(GlanceModifier.width(4.dp))
            Column(GlanceModifier.defaultWeight().clickable(openApp(context, 2))) {
                Text(task.title, maxLines = 1, style = TextStyle(color = if (task.done) colors.onSurfaceVariant else colors.onSurface,
                    fontSize = 14.sp, fontWeight = FontWeight.Medium,
                    textDecoration = if (task.done) androidx.glance.text.TextDecoration.LineThrough else null))
                val kind = context.getString(kindLabel(task.kind))
                val note = if (entry.overdue) context.getString(R.string.was_due,
                    relativeDate(context, task.due!!, today).lowercase(Locale.getDefault())) else kind
                Text(note, maxLines = 1, style = TextStyle(color = if (entry.overdue) colors.error else colors.onSurfaceVariant, fontSize = 12.sp))
            }
        }
    }
}

private fun openApp(context: Context, tab: Int, newTask: Boolean = false) = actionStartActivity(
    Intent(context, MainActivity::class.java).putExtra("tab", tab).putExtra("new_task", newTask)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))

private val TaskUid = ActionParameters.Key<String>("uid")
private val TaskDone = ActionParameters.Key<Boolean>("done")

/** The circle beside a task: marks it done (a tick, struck through) without opening the app;
 *  tapping the tick undoes it. The widget is redrawn here, because the app's own delayed
 *  redraw can be lost once this callback returns and the process is frozen. */
class CompleteTask : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val uid = parameters[TaskUid] ?: return
        val done = parameters[TaskDone] ?: true
        withContext(Dispatchers.IO) { context.container.repository.setDone(uid, done) }
        AgendaWidget().updateAll(context.applicationContext)
    }
}
