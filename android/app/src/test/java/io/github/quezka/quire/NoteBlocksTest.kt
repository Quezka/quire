package io.github.quezka.quire

import io.github.quezka.quire.domain.BlockKind
import io.github.quezka.quire.domain.NoteBlock
import io.github.quezka.quire.domain.NoteBlocks
import org.junit.Assert.assertEquals
import org.junit.Test

/** The phone's note editor: blocks per line, the same Markdown as the desktop writes. */
class NoteBlocksTest {
    private val roundTrips = listOf(
        "# Biology: cellular respiration\n\n**Equation:** C6H12O6 + 6 O2 → energy (~34 ATP)\n\n" +
            "## Stages\n1. Glycolysis\n2. Krebs cycle\n\n- [x] Review p. 112\n- [ ] Ask about it",
        "Some **bold**, *italic*, `code`, ~~gone~~ and [a link](https://x.org).",
        "- top\n    - nested\n        - deeper\n    - back\n- top again\n3. three\n4. four",
        "> quote\n> > deeper",
        "```py\nx = 1\n  y = 2\n\n```\nafter",
        "![ER](quire-image:ab12cd34ab12cd34)\n\nline one\nline two\n---\nend",
        "\\# not a heading\n\\- not a list",
        "",
    )

    @Test fun notesRoundTripExactly() {
        for (body in roundTrips) assertEquals(body, NoteBlocks.write(NoteBlocks.parse(body)))
    }

    @Test fun linesBecomeBlocks() {
        val blocks = NoteBlocks.parse("## Stages\n    - [x] done\n> hi\n![ER](quire-image:ab12cd34)")
        assertEquals(listOf(BlockKind.HEADING, BlockKind.CHECK, BlockKind.QUOTE, BlockKind.IMAGE), blocks.map { it.kind })
        assertEquals(NoteBlock(BlockKind.CHECK, "done", 1, checked = true), blocks[1])
        assertEquals("ab12cd34", blocks[3].extra)
    }

    @Test fun typedPrefixesFormatTheLine() {
        fun typed(t: String) = NoteBlocks.shortcut(NoteBlock(text = t))
        assertEquals(NoteBlock(BlockKind.HEADING, "", 2), typed("## "))
        assertEquals(NoteBlock(BlockKind.BULLET, ""), typed("- "))
        assertEquals(NoteBlock(BlockKind.NUMBERED, "", number = 3), typed("3. "))
        assertEquals(NoteBlock(BlockKind.CHECK, ""), typed("[ ] "))
        assertEquals(NoteBlock(BlockKind.CHECK, "", checked = true), typed("- [x] "))
        assertEquals(NoteBlock(BlockKind.QUOTE, "", 1), typed("> "))
        assertEquals(BlockKind.CODE, typed("```")!!.kind)
        assertEquals(null, typed("#hashtag"))
        assertEquals(NoteBlock(BlockKind.CHECK, ""), NoteBlocks.shortcut(NoteBlock(BlockKind.BULLET, "[ ] ")))
    }

    @Test fun enterContinuesListsAndEndsThemWhenEmpty() {
        var blocks = NoteBlocks.parse("- [x] milk")
        var edit = NoteBlocks.enter(blocks, 0, 4)
        assertEquals("- [x] milk\n- [ ] ", NoteBlocks.write(edit.blocks))
        assertEquals(1 to 0, edit.focus to edit.cursor)
        edit = NoteBlocks.enter(edit.blocks, 1, 0)
        assertEquals("- [x] milk\n", NoteBlocks.write(edit.blocks))
        blocks = NoteBlocks.parse("# Title here")
        edit = NoteBlocks.enter(blocks, 0, 5)
        assertEquals("# Title\n here", NoteBlocks.write(edit.blocks))
        blocks = NoteBlocks.parse("1. one")
        assertEquals("1. one\n2. ", NoteBlocks.write(NoteBlocks.enter(blocks, 0, 3).blocks))
    }

    @Test fun backspaceAtTheStartUnformatsThenJoins() {
        var edit = NoteBlocks.backspace(NoteBlocks.parse("a\n## b"), 1)
        assertEquals("a\nb", NoteBlocks.write(edit.blocks))
        edit = NoteBlocks.backspace(edit.blocks, 1)
        assertEquals("ab", NoteBlocks.write(edit.blocks))
        assertEquals(0 to 1, edit.focus to edit.cursor)
        edit = NoteBlocks.backspace(NoteBlocks.parse("- a\n    - b"), 1)
        assertEquals("- a\n- b", NoteBlocks.write(edit.blocks))
        edit = NoteBlocks.backspace(NoteBlocks.parse("![x](quire-image:ab12cd34)\nafter"), 1)
        assertEquals("after", NoteBlocks.write(edit.blocks))
    }

    @Test fun pastedLinesBecomeBlocks() {
        val edit = NoteBlocks.paste(NoteBlocks.parse("start end"), 0, "start ", "one\n- two\n# three", "end")
        assertEquals("start one\n- two\n# threeend", NoteBlocks.write(edit.blocks))
        assertEquals(2 to 5, edit.focus to edit.cursor)
    }

    @Test fun toolbarAndIndent() {
        val blocks = NoteBlocks.parse("eggs")
        val checklist = NoteBlocks.setKind(blocks, 0, BlockKind.CHECK)
        assertEquals("- [ ] eggs", NoteBlocks.write(checklist))
        assertEquals("    - [ ] eggs", NoteBlocks.write(NoteBlocks.indent(checklist, 0, true)))
        assertEquals("eggs", NoteBlocks.write(NoteBlocks.setKind(checklist, 0, BlockKind.CHECK)))
        assertEquals("## eggs", NoteBlocks.write(NoteBlocks.setKind(blocks, 0, BlockKind.HEADING, 2)))
    }
}
