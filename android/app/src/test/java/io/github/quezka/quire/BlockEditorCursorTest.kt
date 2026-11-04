package io.github.quezka.quire

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.ui.BlockEditor
import io.github.quezka.quire.ui.BlockEditorState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Tapping in a note must put the cursor where the finger is, in a line being edited and in one not yet. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w400dp-h800dp-xhdpi", application = android.app.Application::class)
class BlockEditorCursorTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    private fun show(state: BlockEditorState) = rule.setContent {
        MaterialTheme {
            BlockEditor(state, { null }, "hint",
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp))
        }
    }

    private fun tap(fraction: Float) {
        rule.onAllNodes(hasSetTextAction()).onFirst().performTouchInput {
            click(Offset(width * fraction, height / 2f))
        }
        rule.waitForIdle()
    }

    @Test fun tappingMovesTheCursorInAPlainLine() {
        val state = BlockEditorState("hello world and some more words")
        show(state)
        tap(0.2f)
        val first = state.blocks[0].field.selection.start
        rule.mainClock.advanceTimeBy(1000)
        tap(0.7f)
        val second = state.blocks[0].field.selection.start
        println("plain: $first -> $second")
        assertTrue("the second tap is further along: $first, $second", second > first)
        rule.mainClock.advanceTimeBy(1000)
        tap(0.1f)
        val third = state.blocks[0].field.selection.start
        println("plain back: $third")
        assertTrue("back again: $third < $second", third < second)
    }

    @Test fun tappingMovesTheCursorInALineWithMarks() {
        val state = BlockEditorState("hello **bold words** and *more* of them")
        show(state)
        tap(0.2f)
        val first = state.blocks[0].field.selection.start
        rule.mainClock.advanceTimeBy(1000)
        tap(0.7f)
        val second = state.blocks[0].field.selection.start
        println("marks: $first -> $second")
        assertNotEquals(first, second)
        assertEquals(first < second, true)
    }
}
