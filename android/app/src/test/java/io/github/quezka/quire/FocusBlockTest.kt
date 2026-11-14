package io.github.quezka.quire

import io.github.quezka.quire.domain.FocusSettings
import io.github.quezka.quire.domain.Phase
import io.github.quezka.quire.domain.PomodoroTimer
import io.github.quezka.quire.domain.planBlock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

class FocusBlockTest {
    @Test fun planMatchesTheDesktop() {
        val plan = planBlock(120, FocusSettings())
        assertEquals(120, plan.sumOf { it.second })
        assertEquals(Phase.WORK, plan.last().first)
        assertEquals(listOf(Phase.WORK to 28), planBlock(28, FocusSettings()))
        assertEquals(listOf(Phase.WORK to 25, Phase.SHORT_BREAK to 5, Phase.WORK to 30), planBlock(60, FocusSettings()))
    }

    @Test fun aBlockRunsByItselfAndStopsAtItsEnd() {
        val t = PomodoroTimer(FocusSettings(autoContinue = false))
        val start = Instant.parse("2026-11-14T09:00:00Z")
        t.startBlock(start, 60)
        var now = start
        val ended = mutableListOf<io.github.quezka.quire.domain.PhaseEnded>()
        while (ended.lastOrNull()?.blockDone != true) {
            now = now.plus(Duration.ofSeconds(30))
            t.tick(now)?.let { ended += it }
            assertTrue(now < start.plus(Duration.ofMinutes(70)))
        }
        assertEquals(listOf(Phase.WORK, Phase.SHORT_BREAK, Phase.WORK, Phase.WORK), ended.map { it.phase })
        assertFalse(t.inBlock || t.running)
    }
}
