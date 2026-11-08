package io.github.quezka.quire

import androidx.compose.ui.graphics.Color
import io.github.quezka.quire.ui.InlineStyler
import org.junit.Assert.assertEquals
import org.junit.Test

/** The note editor's mapping between the typed text and what's drawn: where the cursor appears. */
class InlineMappingTest {
    private fun mapping(text: String, hide: Boolean) =
        InlineStyler(text, hide, Color.Blue, Color.Gray, Color.LightGray).transformed()

    @Test fun plainTextMapsEveryCharacterToItself() {
        val text = "Hello world this is a test"
        for (hide in listOf(false, true)) {
            val m = mapping(text, hide).offsetMapping
            for (k in 0..text.length) {
                assertEquals(k, m.originalToTransformed(k))
                assertEquals(k, m.transformedToOriginal(k))
            }
        }
    }

    @Test fun hiddenMarksCollapseButTheWordsKeepTheirPlaces() {
        val text = "a **bold** b"
        val t = mapping(text, hide = true)
        assertEquals("a bold b", t.text.text)
        val m = t.offsetMapping
        assertEquals(2, m.originalToTransformed(2))  // before the marks
        assertEquals(2, m.originalToTransformed(4))  // "b" of bold
        assertEquals(4, m.originalToTransformed(6))  // "l"
        assertEquals(6, m.originalToTransformed(10)) // the space after
        assertEquals(text.length - 4, m.originalToTransformed(text.length))
        // Shown faded while editing: identity again.
        val shown = mapping(text, hide = false).offsetMapping
        for (k in 0..text.length) assertEquals(k, shown.originalToTransformed(k))
    }
}
