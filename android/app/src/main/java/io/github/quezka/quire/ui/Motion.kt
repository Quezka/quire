package io.github.quezka.quire.ui

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.ContentTransform
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.ui.unit.IntOffset

/** Quire's motion: short, soft and consistent across screens. */
object Motion {
    const val SHORT = 180
    const val MEDIUM = 280

    fun <T> gentle() = spring<T>(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessMediumLow)
    fun <T> bouncy() = spring<T>(dampingRatio = Spring.DampingRatioLowBouncy, stiffness = Spring.StiffnessMedium)
    val offset = spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessMediumLow,
        visibilityThreshold = IntOffset(1, 1))

    /** Between the bottom tabs: a quick fade with a slight rise. */
    fun tabs(): ContentTransform =
        (fadeIn(tween(MEDIUM, easing = FastOutSlowInEasing)) + scaleIn(tween(MEDIUM), initialScale = 0.98f))
            .togetherWith(fadeOut(tween(SHORT)))

    /** Into a page and back out: slides the way you're going. */
    fun <S> AnimatedContentTransitionScope<S>.push(forward: Boolean): ContentTransform {
        val dir = if (forward) 1 else -1
        return (slideInHorizontally(offset) { it / 3 * dir } + fadeIn(tween(MEDIUM)))
            .togetherWith(slideOutHorizontally(offset) { -it / 5 * dir } + fadeOut(tween(SHORT)))
    }
}

/** Shrinks a touch while pressed, for cards and rows. */
@Composable
fun Modifier.pressScale(source: MutableInteractionSource): Modifier {
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.97f else 1f, Motion.bouncy(), label = "press")
    return graphicsLayer { scaleX = scale; scaleY = scale }
}
