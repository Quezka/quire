package io.github.quezka.quire.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.luminance
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeStyle
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.haze
import dev.chrisbanes.haze.hazeChild

/** Room the glass bottom bar takes over the pages: lists add it at their end, so nothing stays hidden under it. */
val LocalBottomInset = compositionLocalOf { 0.dp }

/** The glass the bars are made of: a strong blur of what's under them with only a light tint, so what's beneath
 *  clearly shows through (the user asked for real transparency) while the bar's text stays readable. */
@Composable
fun glassStyle(): HazeStyle {
    val c = MaterialTheme.colorScheme
    val dark = c.background.luminance() < 0.5f
    return HazeStyle(
        backgroundColor = c.background,
        tint = HazeTint(c.surface.copy(alpha = if (dark) 0.30f else 0.22f)),
        blurRadius = 28.dp,
        noiseFactor = 0f,
        fallbackTint = HazeTint(c.surface.copy(alpha = 0.94f)),
    )
}

/**
 * A main screen in the glass style: `bar` floats at the top and blurs the content that scrolls under it. The content
 * gets the padding to start below the bar and end above the bottom navigation; lists should use it as their
 * contentPadding (plus their own), so they can scroll under both.
 */
@Composable
fun GlassScreen(bar: @Composable () -> Unit, content: @Composable (PaddingValues) -> Unit) {
    val haze = remember { HazeState() }
    val density = LocalDensity.current
    var barPx by remember { mutableIntStateOf(0) }
    val top: Dp = with(density) { barPx.toDp() }
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().haze(haze)) {
            content(PaddingValues(top = top, bottom = LocalBottomInset.current))
        }
        Column(Modifier.fillMaxWidth().hazeChild(haze, glassStyle()).onSizeChanged { barPx = it.height }) {
            bar()
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f))
        }
    }
}

/** Adds a screen's own padding to the glass padding. */
fun PaddingValues.plus(start: Dp = 0.dp, top: Dp = 0.dp, end: Dp = 0.dp, bottom: Dp = 0.dp): PaddingValues =
    PaddingValues(start = start, top = calculateTopPadding() + top, end = end,
        bottom = calculateBottomPadding() + bottom)

/** Top app bars sit on glass, so their own container is clear. */
val ClearBar = Color.Transparent
