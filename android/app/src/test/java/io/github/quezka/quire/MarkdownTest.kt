package io.github.quezka.quire

import io.github.quezka.quire.domain.Markdown
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MarkdownTest {
    @Test fun enterContinuesAListAndEndsItOnAnEmptyItem() {
        assertEquals("- milk\n- " to 9, Markdown.continueList("- milk", "- milk\n", 7))
        assertEquals("  3. a\n  4. " to 12, Markdown.continueList("  3. a", "  3. a\n", 7))
        assertEquals("- [x] done\n- [ ] " to 17, Markdown.continueList("- [x] done", "- [x] done\n", 11))
        assertEquals("- milk\n" to 7, Markdown.continueList("- milk\n- ", "- milk\n- \n", 10))
        assertNull(Markdown.continueList("plain", "plain\n", 6)) // not a list
        assertNull(Markdown.continueList("- a", "- ab", 4)) // not a newline
    }

    @Test fun checkboxesToggle() {
        assertEquals("x\n- [x] b", Markdown.toggleCheckbox("x\n- [ ] b", 1))
        assertEquals("- [ ] b", Markdown.toggleCheckbox("- [X] b", 0))
        assertEquals("plain", Markdown.toggleCheckbox("plain", 0))
    }

    @Test fun wrapAndPrefix() {
        assertEquals(Triple("a **b** c", 4, 5), Markdown.wrap("a b c", 2, 3, "**", "bold"))
        assertEquals(Triple("a b c", 2, 3), Markdown.wrap("a **b** c", 2, 7, "**", "bold"))
        assertEquals("- [ ] eggs\n- [ ] flour", Markdown.togglePrefix("eggs\nflour", 0, 10, "- [ ] ").first)
        assertEquals("eggs\nflour", Markdown.togglePrefix("- eggs\n- flour", 0, 14, "- ").first)
        assertEquals("title\n## sub", Markdown.togglePrefix("title\nsub", 7, 7, "## ").first)
    }

    @Test fun snippetMatchesTheDesktop() {
        assertEquals("The powerhouse of the cell see p. 4",
            Markdown.snippet("# Mitochondria\n\nThe **powerhouse** of the cell\n- [ ] see [p. 4](http://x)"))
        assertEquals("Nature vs. nurture and this", Markdown.snippet("T\n*Nature vs. nurture* and _this_"))
    }

    @Test fun ocrTextIsTidied() {
        val raw = "La cellula è l'unità fonda-\nmentale della vita. Tutti gli\norganismi sono fatti di cellule.\n\n- nucleo\n- mitocondri\n"
        assertEquals("La cellula è l'unità fondamentale della vita. Tutti gli organismi sono fatti di cellule.\n\n- nucleo\n- mitocondri",
            Markdown.tidyOcr(raw))
    }
}
