package io.github.quezka.quire.widget

import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.appWidgetBackground
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.lazy.LazyColumn
import androidx.glance.appwidget.lazy.items
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.updateAll
import androidx.glance.background
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import io.github.quezka.quire.MainActivity
import io.github.quezka.quire.R
import io.github.quezka.quire.container
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Home-screen notes (0.52): pinned first, then the latest; tap one to open it. */
class NotesWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact

    data class Row(val uid: String, val title: String, val preview: String, val pinned: Boolean)

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val rows = withContext(Dispatchers.IO) {
            context.container.repository.notes().take(MAX).map { n ->
                val lines = n.body.lines().map { it.trim().trimStart('#', '-', '*', ' ') }.filter { it.isNotBlank() }
                Row(n.uid, n.title, lines.drop(1).firstOrNull().orEmpty(), n.pinned)
            }
        }
        provideContent {
            GlanceTheme(if (Build.VERSION.SDK_INT >= 31) GlanceTheme.colors else QuireWidgetColors) { NotesContent(context, rows) }
        }
    }

    companion object {
        const val MAX = 12
        private var pending: Job? = null
        fun refresh(context: Context) {
            val app = context.applicationContext
            pending?.cancel()
            pending = AgendaWidget.scope.launch { delay(400); NotesWidget().updateAll(app) }
        }
    }
}

private fun openNote(context: Context, uid: String) = actionStartActivity(
    Intent(context, MainActivity::class.java).putExtra("note", uid)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        .setData(android.net.Uri.parse("quire-note:$uid"))) // unique per row <- else one PendingIntent for all

@Composable
private fun NotesContent(context: Context, rows: List<NotesWidget.Row>) {
    val c = GlanceTheme.colors
    Column(GlanceModifier.fillMaxSize().appWidgetBackground().background(c.widgetBackground).cornerRadius(24.dp).padding(12.dp)) {
        Row(GlanceModifier.fillMaxWidth().clickable(openNote(context, "")).padding(horizontal = 4.dp, vertical = 4.dp)) {
            Text(context.getString(R.string.notes_widget_title),
                style = TextStyle(color = c.onSurface, fontSize = 18.sp, fontWeight = FontWeight.Bold))
        }
        Spacer(GlanceModifier.height(6.dp))
        if (rows.isEmpty()) Text(context.getString(R.string.notes_widget_empty),
            GlanceModifier.padding(4.dp), style = TextStyle(color = c.onSurfaceVariant, fontSize = 15.sp))
        LazyColumn(GlanceModifier.fillMaxSize()) {
            items(rows, itemId = { it.uid.hashCode().toLong() }) { row ->
                Column(GlanceModifier.fillMaxWidth().padding(bottom = 6.dp)) {
                    Column(GlanceModifier.fillMaxWidth().background(c.secondaryContainer).cornerRadius(14.dp)
                        .padding(horizontal = 12.dp, vertical = 8.dp).clickable(openNote(context, row.uid))) {
                        Text((if (row.pinned) "• " else "") + row.title, maxLines = 1,
                            style = TextStyle(color = c.onSecondaryContainer, fontSize = 16.sp, fontWeight = FontWeight.Medium))
                        if (row.preview.isNotBlank()) Text(row.preview, maxLines = 2,
                            style = TextStyle(color = c.onSecondaryContainer, fontSize = 14.sp))
                    }
                }
            }
        }
    }
}

class NotesWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = NotesWidget()
}
