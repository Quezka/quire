package io.github.quezka.quire.widget

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.lazy.LazyColumn
import androidx.glance.appwidget.lazy.items
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.color.ColorProvider
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
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val repo = context.container.repository
        val (now, days) = withContext(Dispatchers.IO) {
            repo.now() to WidgetAgenda.build(repo.now(), repo.courses(), repo.events(), repo.jobs(),
                repo.shifts(), repo.tasks())
        }
        provideContent { GlanceTheme { Content(context, now.toLocalDate(), days) } }
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

private val Ink = ColorProvider(day = Color(0xFF16181D), night = Color(0xFFECEDEF))
private val Muted = ColorProvider(day = Color(0xFF636A75), night = Color(0xFF9BA1AB))
private val Surface = ColorProvider(day = Color(0xFFFFFFFF), night = Color(0xFF18191C))
private val Accent = ColorProvider(day = Color(0xFF5B5BD6), night = Color(0xFF8182F0))
private val Alert = ColorProvider(day = Color(0xFFE5484D), night = Color(0xFFFF6369))

@Composable
private fun Content(context: Context, today: LocalDate, days: List<WidgetDay>) {
    Column(GlanceModifier.fillMaxSize().background(Surface).cornerRadius(20.dp)) {
        Row(GlanceModifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Column(GlanceModifier.defaultWeight().clickable(openApp(context, 0))) {
                Text(today.format(DateTimeFormatter.ofPattern("EEEE", Locale.getDefault()))
                    .replaceFirstChar { it.titlecase(Locale.getDefault()) },
                    style = TextStyle(color = Accent, fontSize = 12.sp, fontWeight = FontWeight.Medium))
                Text(today.format(DateTimeFormatter.ofPattern("d MMMM", Locale.getDefault())),
                    style = TextStyle(color = Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold))
            }
            Box(GlanceModifier.size(40.dp).clickable(openApp(context, 2, newTask = true)),
                contentAlignment = Alignment.Center) {
                Image(ImageProvider(R.drawable.ic_widget_add), context.getString(R.string.add_task),
                    GlanceModifier.size(28.dp))
            }
        }
        if (days.isEmpty()) {
            Box(GlanceModifier.fillMaxSize().clickable(openApp(context, 0)), contentAlignment = Alignment.Center) {
                Text(context.getString(R.string.widget_empty),
                    style = TextStyle(color = Muted, fontSize = 14.sp))
            }
        } else {
            LazyColumn(GlanceModifier.fillMaxSize().padding(horizontal = 8.dp)) {
                for (day in days) {
                    item {
                        Text(relativeDate(context, day.day, today).uppercase(Locale.getDefault()),
                            GlanceModifier.fillMaxWidth().padding(start = 8.dp, top = 8.dp, bottom = 2.dp),
                            style = TextStyle(color = Muted, fontSize = 11.sp, fontWeight = FontWeight.Medium))
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
private fun TimedRow(context: Context, entry: WidgetEntry.Timed) {
    val item = entry.item
    val tag = when (item.kind) {
        ItemKind.CLASS -> item.room
        ItemKind.EVENT -> ""
        ItemKind.SHIFT -> context.getString(R.string.kind_shift)
    }
    Row(GlanceModifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)
        .clickable(openApp(context, 0)),
        verticalAlignment = Alignment.CenterVertically) {
        Box(GlanceModifier.width(4.dp).height(32.dp).background(parseColor(item.color)).cornerRadius(2.dp)) {}
        Spacer(GlanceModifier.width(10.dp))
        Column(GlanceModifier.defaultWeight()) {
            Text(item.title, maxLines = 1, style = TextStyle(color = Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium))
            Text(listOf("${minutes(item.start)}–${minutes(item.end)}", tag).filter { it.isNotBlank() }.joinToString(" · "),
                maxLines = 1, style = TextStyle(color = Muted, fontSize = 12.sp))
        }
    }
}

@Composable
private fun DueRow(context: Context, entry: WidgetEntry.Due, today: LocalDate) {
    val task = entry.task
    Row(GlanceModifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(GlanceModifier.size(32.dp).clickable(actionRunCallback<CompleteTask>(
            actionParametersOf(TaskUid to task.uid))), contentAlignment = Alignment.Center) {
            Image(ImageProvider(R.drawable.ic_widget_circle), context.getString(R.string.mark_done),
                GlanceModifier.size(20.dp))
        }
        Spacer(GlanceModifier.width(6.dp))
        Column(GlanceModifier.defaultWeight().clickable(openApp(context, 2))) {
            Text(task.title, maxLines = 1, style = TextStyle(color = Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium))
            val kind = context.getString(kindLabel(task.kind))
            val note = if (entry.overdue) context.getString(R.string.was_due,
                relativeDate(context, task.due!!, today).lowercase(Locale.getDefault())) else kind
            Text(note, maxLines = 1, style = TextStyle(color = if (entry.overdue) Alert else Muted, fontSize = 12.sp))
        }
    }
}

private fun openApp(context: Context, tab: Int, newTask: Boolean = false) = actionStartActivity(
    Intent(context, MainActivity::class.java).putExtra("tab", tab).putExtra("new_task", newTask)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))

private val TaskUid = ActionParameters.Key<String>("uid")

/** The circle beside a task: marks it done without opening the app. */
class CompleteTask : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val uid = parameters[TaskUid] ?: return
        withContext(Dispatchers.IO) { context.container.repository.setDone(uid, true) }
    }
}
