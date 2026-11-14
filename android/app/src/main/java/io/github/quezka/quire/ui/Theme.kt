package io.github.quezka.quire.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight

import io.github.quezka.quire.R

private val Manrope = FontFamily(
    Font(R.font.manrope_regular, FontWeight.Normal), Font(R.font.manrope_medium, FontWeight.Medium),
    Font(R.font.manrope_semibold, FontWeight.SemiBold), Font(R.font.manrope_bold, FontWeight.Bold),
)

/** Material's type scale in the suite's typeface. */
private val SuiteType = SuiteTokens.typography(Manrope)

/** The suite's palette, the same as the desktop's (quezka_ui/theme.py), Cadence's and Vesper's. */
internal val Light = SuiteTokens.Light

internal val Dark = SuiteTokens.Dark

/** Material 3 tonal, as across the suite (since 0.47): solid bars and cards, no blur. */
object Glass {
    /** A content surface: solid, as content is in Apple's glass design. */
    @Composable
    fun surface(): Color = MaterialTheme.colorScheme.surfaceContainerLow

    /** Content cards have no outline of their own. */
    @Composable
    fun edge(): androidx.compose.foundation.BorderStroke? = null
}

@Composable
fun QuireTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, typography = SuiteType, content = content)
}

fun parseColor(hex: String): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Color(0xFF5B5BD6))
