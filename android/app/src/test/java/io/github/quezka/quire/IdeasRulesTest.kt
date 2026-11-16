package io.github.quezka.quire

import io.github.quezka.quire.domain.Idea
import io.github.quezka.quire.domain.Ideas
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime

/** Same cases as the desktop's tests/test_ideas.py. */
class IdeasRulesTest {
    @Test fun tagsAreWordsInTheText() {
        assertEquals(listOf("3ds", "home"), Ideas.tags("A shelf for the #3DS games #home #Home"))
        assertEquals(listOf("12"), Ideas.tags("issue #12 and a#b"))
    }

    @Test fun searchNeedsEveryWordAndTag() {
        val idea = Idea("u", "Ask Sam about the #school trip", LocalDateTime.of(2026, 11, 1, 9, 0))
        assertTrue(Ideas.matches(idea, "sam trip"))
        assertTrue(Ideas.matches(idea, "#school"))
        assertFalse(Ideas.matches(idea, "#game"))
        assertTrue(Ideas.matches(idea, ""))
    }

    @Test fun anOldOpenIdeaComesBack() {
        val today = LocalDate.of(2026, 11, 15)
        val old = Idea("1", "old", LocalDateTime.of(2026, 11, 1, 9, 0))
        val older = Idea("2", "older", LocalDateTime.of(2026, 10, 1, 9, 0))
        val fresh = Idea("3", "fresh", LocalDateTime.of(2026, 11, 14, 9, 0))
        assertEquals("2", Ideas.resurface(listOf(old, older, fresh), today, emptyMap())?.uid)
        assertEquals("1", Ideas.resurface(listOf(old, older), today, mapOf("2" to "2026-11-10"))?.uid)
        assertNull(Ideas.resurface(listOf(older), today, mapOf("2" to "2026-11-12")))
    }

    @Test fun taskTitleIsTheFirstLineWithoutTags() {
        assertEquals("Buy paint", Ideas.firstLine("Buy #home paint\nwhite, 2 l"))
        assertTrue(Ideas.firstLine("word ".repeat(50), 20).endsWith("…"))
    }
}
