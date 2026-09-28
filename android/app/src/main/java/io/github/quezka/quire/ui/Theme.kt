package io.github.quezka.quire.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** The desktop's palette (quire/presentation/theme.py). */
private val Light = lightColorScheme(
    primary = Color(0xFF5B5BD6), onPrimary = Color.White,
    primaryContainer = Color(0xFFE6E6FB), onPrimaryContainer = Color(0xFF3B3BA8),
    secondaryContainer = Color(0xFFE6E6FB), onSecondaryContainer = Color(0xFF3B3BA8),
    background = Color(0xFFF5F6F8), onBackground = Color(0xFF16181D),
    surface = Color(0xFFF5F6F8), onSurface = Color(0xFF16181D),
    surfaceVariant = Color(0xFFF0F1F4), onSurfaceVariant = Color(0xFF636A75),
    surfaceContainer = Color(0xFFECEEF2), surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFFFFFFF), surfaceContainerHighest = Color(0xFFF0F1F4),
    outline = Color(0xFFC9CCD3), outlineVariant = Color(0xFFE2E4E9),
    error = Color(0xFFE5484D), tertiary = Color(0xFF30A46C),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF8182F0), onPrimary = Color.White,
    primaryContainer = Color(0xFF262747), onPrimaryContainer = Color(0xFFC9CAFB),
    secondaryContainer = Color(0xFF262747), onSecondaryContainer = Color(0xFFC9CAFB),
    background = Color(0xFF111214), onBackground = Color(0xFFECEDEF),
    surface = Color(0xFF111214), onSurface = Color(0xFFECEDEF),
    surfaceVariant = Color(0xFF202226), onSurfaceVariant = Color(0xFF9BA1AB),
    surfaceContainer = Color(0xFF141517), surfaceContainerLow = Color(0xFF18191C),
    surfaceContainerHigh = Color(0xFF18191C), surfaceContainerHighest = Color(0xFF202226),
    outline = Color(0xFF3A3D44), outlineVariant = Color(0xFF2A2C31),
    error = Color(0xFFFF6369), tertiary = Color(0xFF3DD68C),
)

@Composable
fun QuireTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}

fun parseColor(hex: String): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Color(0xFF5B5BD6))
