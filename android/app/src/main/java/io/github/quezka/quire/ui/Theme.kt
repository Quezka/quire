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
private val SuiteType = Typography().run {
    copy(displayLarge.copy(fontFamily = Manrope), displayMedium.copy(fontFamily = Manrope), displaySmall.copy(fontFamily = Manrope),
        headlineLarge.copy(fontFamily = Manrope), headlineMedium.copy(fontFamily = Manrope), headlineSmall.copy(fontFamily = Manrope),
        titleLarge.copy(fontFamily = Manrope), titleMedium.copy(fontFamily = Manrope), titleSmall.copy(fontFamily = Manrope),
        bodyLarge.copy(fontFamily = Manrope), bodyMedium.copy(fontFamily = Manrope), bodySmall.copy(fontFamily = Manrope),
        labelLarge.copy(fontFamily = Manrope), labelMedium.copy(fontFamily = Manrope), labelSmall.copy(fontFamily = Manrope))
}

/** The suite's palette, the same as the desktop's (quezka_ui/theme.py), Cadence's and Vesper's. */
internal val Light = lightColorScheme(
    primary = Color(0xFF4F46E5), onPrimary = Color.White,
    primaryContainer = Color(0xFFDCDBFF), onPrimaryContainer = Color(0xFF1E1A78),
    secondaryContainer = Color(0xFFDCDBFF), onSecondaryContainer = Color(0xFF1E1A78),
    background = Color(0xFFF3F2FF), onBackground = Color(0xFF0B0D14),
    surface = Color(0xFFF3F2FF), onSurface = Color(0xFF0B0D14),
    surfaceVariant = Color(0xFFE9E8FF), onSurfaceVariant = Color(0xFF343B4D),
    surfaceContainer = Color(0xFFECEAFF), surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFFFFFFF), surfaceContainerHighest = Color(0xFFE9E8FF),
    outline = Color(0xFFB3B6CC), outlineVariant = Color(0xFFDEDCF7),
    error = Color(0xFFD0262D), tertiary = Color(0xFF127A46),
)

internal val Dark = darkColorScheme(
    primary = Color(0xFFA9A6FF), onPrimary = Color(0xFF0B0B14),
    primaryContainer = Color(0xFF3B3984), onPrimaryContainer = Color(0xFFE4E3FF),
    secondaryContainer = Color(0xFF3B3984), onSecondaryContainer = Color(0xFFE4E3FF),
    background = Color(0xFF0E0E19), onBackground = Color(0xFFF6F7FB),
    surface = Color(0xFF0E0E19), onSurface = Color(0xFFF6F7FB),
    surfaceVariant = Color(0xFF27273F), onSurfaceVariant = Color(0xFFCBCFDD),
    surfaceContainer = Color(0xFF13131F), surfaceContainerLow = Color(0xFF1A1A2B),
    surfaceContainerHigh = Color(0xFF1A1A2B), surfaceContainerHighest = Color(0xFF27273F),
    outline = Color(0xFF4B4E66), outlineVariant = Color(0xFF2D2D47),
    error = Color(0xFFFF7B80), tertiary = Color(0xFF4ADE80),
)

/**
 * Liquid glass, Apple style, as across the suite: backgrounds and content stay solid, and the bars that float over
 * content (the top bar of the main screens, the bottom navigation) blur what scrolls under them. See `Glass.kt`.
 */
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
