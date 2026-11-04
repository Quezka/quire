package io.github.quezka.quire

import android.graphics.Bitmap
import android.view.View
import android.widget.FrameLayout
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.background
import androidx.glance.layout.Column
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import androidx.glance.appwidget.ExperimentalGlanceRemoteViewsApi
import androidx.glance.appwidget.GlanceRemoteViews
import io.github.quezka.quire.domain.AgendaItem
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.domain.WidgetDay
import io.github.quezka.quire.domain.WidgetEntry
import io.github.quezka.quire.widget.AgendaContent
import io.github.quezka.quire.widget.DueRow
import io.github.quezka.quire.widget.TimedRow
import io.github.quezka.quire.widget.QuireWidgetColors
import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.time.LocalDate

/** The widget really composes into RemoteViews (Glance throws on what it can't draw); with SCREENSHOTS=1 it's also drawn. */
@OptIn(ExperimentalGlanceRemoteViewsApi::class)
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w400dp-h860dp-xxhdpi", application = android.app.Application::class)
class WidgetScreenshotTest {
    private val today = LocalDate.of(2026, 9, 23)

    private fun shot(name: String, size: DpSize, days: List<WidgetDay>) {
        val context = RuntimeEnvironment.getApplication()
        render(name, size) { AgendaContent(context, today, days) }
    }

    private fun render(name: String, size: DpSize, content: @Composable () -> Unit): Unit = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val result = GlanceRemoteViews().compose(context, size) { GlanceTheme(QuireWidgetColors) { content() } }
        if (System.getenv("SCREENSHOTS") == null) return@runBlocking
        val density = context.resources.displayMetrics.density
        val w = (size.width.value * density).toInt(); val h = (size.height.value * density).toInt()
        val view = result.remoteViews.apply(context, FrameLayout(context))
        view.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(h, View.MeasureSpec.EXACTLY))
        view.layout(0, 0, w, h)
        val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(0xFF8888AA.toInt())
        view.draw(android.graphics.Canvas(bitmap))
        val out = File("build/screenshots").apply { mkdirs() }.resolve("$name.png")
        out.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private val days = listOf(
        WidgetDay(today, listOf(
            WidgetEntry.Timed(AgendaItem(ItemKind.CLASS, null, today, 510, 560, "Mathematics", "#4466EE", "B12")),
            WidgetEntry.Due(Task("a", "Problem set 3"), overdue = false),
            WidgetEntry.Due(Task("b", "Lab report", due = today.minusDays(1)), overdue = true),
            WidgetEntry.Due(Task("c", "Buy a calculator", done = true), overdue = false))),
        WidgetDay(today.plusDays(1), listOf(
            WidgetEntry.Timed(AgendaItem(ItemKind.EVENT, null, today.plusDays(1), 720, 765, "Lunch with Sam", "#886644")))),
    )

    /** The list itself needs a launcher to fill it, so its rows are drawn on their own. */
    @Test fun theRows() {
        val context = RuntimeEnvironment.getApplication()
        render("widget_rows", DpSize(340.dp, 300.dp)) {
            Column(GlanceModifier.fillMaxSize().background(GlanceTheme.colors.widgetBackground).padding(10.dp)) {
                for (entry in days[0].entries) when (entry) {
                    is WidgetEntry.Timed -> TimedRow(context, entry)
                    is WidgetEntry.Due -> DueRow(context, entry, today)
                }
            }
        }
    }

    @Test fun theWidgetComposes() { shot("widget", DpSize(360.dp, 340.dp), days) }
    @Test fun aShortWidgetComposes() { shot("widget_short", DpSize(300.dp, 120.dp), days) }
    @Test fun anEmptyWidgetComposes() { shot("widget_empty", DpSize(300.dp, 200.dp), emptyList()) }
}
