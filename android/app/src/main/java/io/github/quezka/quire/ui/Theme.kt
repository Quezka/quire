package io.github.quezka.quire.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
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
    primary = Color(0xFF4B4BC8), onPrimary = Color.White,
    primaryContainer = Color(0xFFDDDCFB), onPrimaryContainer = Color(0xFF23236E),
    secondaryContainer = Color(0xFFDDDCFB), onSecondaryContainer = Color(0xFF23236E),
    background = Color(0xFFF6F5FC), onBackground = Color(0xFF0E1116),
    surface = Color(0xFFF6F5FC), onSurface = Color(0xFF0E1116),
    surfaceVariant = Color(0xFFE9E8F6), onSurfaceVariant = Color(0xFF3F4654),
    surfaceContainer = Color(0xFFEEEDF8), surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFFFFFFF), surfaceContainerHighest = Color(0xFFE9E8F6),
    outline = Color(0xFFB9BEC9), outlineVariant = Color(0xFFDFE2EA),
    error = Color(0xFFC4262C), tertiary = Color(0xFF1F7A4D),
)

internal val Dark = darkColorScheme(
    primary = Color(0xFF9A9BFF), onPrimary = Color(0xFF0E0F11),
    primaryContainer = Color(0xFF35366B), onPrimaryContainer = Color(0xFFE2E2FF),
    secondaryContainer = Color(0xFF35366B), onSecondaryContainer = Color(0xFFE2E2FF),
    background = Color(0xFF111119), onBackground = Color(0xFFF4F5F7),
    surface = Color(0xFF111119), onSurface = Color(0xFFF4F5F7),
    surfaceVariant = Color(0xFF28283A), onSurfaceVariant = Color(0xFFC3C8D2),
    surfaceContainer = Color(0xFF16161F), surfaceContainerLow = Color(0xFF1B1B25),
    surfaceContainerHigh = Color(0xFF1B1B25), surfaceContainerHighest = Color(0xFF28283A),
    outline = Color(0xFF4A4E57), outlineVariant = Color(0xFF2C2F35),
    error = Color(0xFFFF7B80), tertiary = Color(0xFF4FE39B),
)

@Composable
fun QuireTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, typography = SuiteType, content = content)
}

fun parseColor(hex: String): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Color(0xFF5B5BD6))
