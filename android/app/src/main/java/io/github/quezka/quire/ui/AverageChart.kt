package io.github.quezka.quire.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.domain.Grade
import io.github.quezka.quire.domain.runningAverage

/** Marks as dots, running average as a line, pass mark dashed (= desktop `TrendChart`). */
@Composable
fun AverageChart(grades: List<Grade>, passMark: Double, height: Int = 160) {
    val c = MaterialTheme.colorScheme
    val marks = grades.filter { it.counts }.sortedBy { it.day }
    val line = runningAverage(marks)
    if (marks.size < 2) return
    val low = minOf(marks.minOf { it.value!! }, passMark) - 0.5
    val high = 10.0
    val first = marks.first().day
    val span = maxOf(java.time.temporal.ChronoUnit.DAYS.between(first, marks.last().day), 1L).toFloat()
    Canvas(Modifier.fillMaxWidth().height(height.dp)) {
        fun point(day: java.time.LocalDate, v: Double) = Offset(
            size.width * java.time.temporal.ChronoUnit.DAYS.between(first, day) / span,
            (size.height - size.height * (v - low) / (high - low)).toFloat())
        val passY = point(first, passMark).y
        drawLine(c.error, Offset(0f, passY), Offset(size.width, passY), strokeWidth = 2f,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 10f)))
        val path = Path()
        line.forEachIndexed { i, (d, v) -> val p = point(d, v); if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y) }
        drawPath(path, c.primary, style = Stroke(width = 6f))
        for (g in marks) drawCircle(if (g.value!! < passMark) c.error else c.onSurface, 8f, point(g.day, g.value))
    }
}
