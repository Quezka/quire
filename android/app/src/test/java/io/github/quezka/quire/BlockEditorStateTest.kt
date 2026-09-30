package io.github.quezka.quire

import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import io.github.quezka.quire.domain.BlockKind
import io.github.quezka.quire.ui.BlockEditorState
import org.junit.Assert.assertEquals
import org.junit.Test

/** Typing into the phone's note editor, as the keyboard delivers it. */
class BlockEditorStateTest {
    private fun BlockEditorState.type(index: Int, text: String, cursor: Int = text.length) =
        typed(index, TextFieldValue(text, TextRange(cursor)))

    @Test fun typingAndEnterBuildTheNote() {
        var changes = 0
        val s = BlockEditorState("") { changes++ }
        s.type(0, "# ")
        assertEquals(BlockKind.HEADING, s.blocks[0].block.kind)
        s.type(0, "Title")
        s.type(0, "Title\n", 6)  // Enter
        s.type(1, "- ")
        s.type(1, "milk")
        s.type(1, "milk\n", 5)
        s.type(2, "eggs")
        assertEquals("# Title\n- milk\n- eggs", s.markdown())
        assertEquals(3, s.words)
        assert(changes > 0)
    }

    @Test fun enterSplitsALineAtTheCursor() {
        val s = BlockEditorState("hello world")
        s.type(0, "hello\n world", 6)
        assertEquals("hello\n world", s.markdown())
        assertEquals(s.blocks[1].id, s.pendingFocus?.first)
    }

    @Test fun pastedLinesBecomeBlocks() {
        val s = BlockEditorState("start end")
        s.type(0, "start one\n- two\nend", 16)
        assertEquals("start one\n- two\nend", s.markdown())
        assertEquals(BlockKind.BULLET, s.blocks[1].block.kind)
    }

    @Test fun backspaceAndChecksAndToolbar() {
        val s = BlockEditorState("a\n- [ ] b")
        s.toggleCheck(1)
        assertEquals("a\n- [x] b", s.markdown())
        s.backspace(1)
        assertEquals("a\nb", s.markdown())
        s.backspace(1)
        assertEquals("ab", s.markdown())
        s.focused = s.blocks[0].id
        s.setKind(BlockKind.QUOTE, 1)
        assertEquals("> ab", s.markdown())
        s.blocks[0].field = TextFieldValue("ab", TextRange(2))
        s.wrap("**", "bold")
        assertEquals("> ab**bold**", s.markdown())
    }

    @Test fun scannedTextGoesWhereTheCursorIs() {
        val s = BlockEditorState("# Notes\nend")
        s.focused = s.blocks[0].id
        s.blocks[0].field = TextFieldValue("Notes", TextRange(5))  // cursor after "Notes"
        s.insertText("line one\nline two")
        assertEquals("# Notes\nline one\nline two\nend", s.markdown())
    }
}
