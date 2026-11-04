package io.github.quezka.quire.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import java.time.LocalDate

/** One day of a chart. [value] is 0 for a day with nothing logged: the slot stays, empty. */
data class DayBar(val day: LocalDate, val value: Int, val colour: Color, val text: String = "")

/** A bar for each day with its amount and date under it, the goal as a line. Tap a day to pick it. */
@Composable
fun DayBars(bars: List<DayBar>, goal: Int, selected: LocalDate?, onPick: (LocalDate) -> Unit, height: Int = 130) {
    val c = MaterialTheme.colorScheme
    val top = maxOf(goal, bars.maxOfOrNull { it.value } ?: 0, 1) * 1.1f
    Row(Modifier.fillMaxWidth()) {
            for (bar in bars) Column(Modifier.weight(1f)
                .background(if (bar.day == selected) c.secondaryContainer else Color.Transparent, RoundedCornerShape(8.dp))
                .clickable { onPick(bar.day) }) {
                Text(bar.text, Modifier.fillMaxWidth(), style = MaterialTheme.typography.labelSmall,
                    textAlign = TextAlign.Center, maxLines = 1, softWrap = false, color = c.onSurface)
                Canvas(Modifier.fillMaxWidth().height(height.dp)) {
                    val y = size.height - goal / top * size.height
                    if (goal > 0) drawLine(c.outline, Offset(0f, y), Offset(size.width, y), strokeWidth = 2f)
                    val h = bar.value / top * size.height
                    if (h > 0) drawRoundRect(bar.colour, Offset(size.width * 0.2f, size.height - h),
                        Size(size.width * 0.6f, h), CornerRadius(8f))
                }
                val last = bar === bars.last()
                Text(bar.day.dayOfMonth.toString(), Modifier.fillMaxWidth(), style = MaterialTheme.typography.labelSmall,
                    textAlign = TextAlign.Center, maxLines = 1, softWrap = false,
                    fontWeight = if (last) FontWeight.Bold else null,
                    color = if (last) c.onSurface else c.onSurfaceVariant)
            }
    }
}
