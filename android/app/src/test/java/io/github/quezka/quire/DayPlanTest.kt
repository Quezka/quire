package io.github.quezka.quire

import io.github.quezka.quire.domain.DayPlan
import org.junit.Assert.assertEquals
import org.junit.Test

/** Same cases as the desktop's tests/test_day_plan.py. */
class DayPlanTest {
    @Test fun gapsLeaveRoomAroundWhatsOn() {
        assertEquals(listOf(480 to 530, 610 to 720), DayPlan.freeGaps(listOf(540 to 600), 480, 720))
        assertEquals(emptyList<Pair<Int, Int>>(), DayPlan.freeGaps(listOf(400 to 700), 480, 600))
    }

    @Test fun tasksGoInOrderIntoTheFirstStretchTheyFit() {
        val slots = DayPlan.plan(listOf("1" to "Essay", "2" to "Maths", "3" to "Call"), listOf(510 to 720, 780 to 840), 480, 1080)
        assertEquals(listOf(850, 905, 960), slots.map { it.start })
        assertEquals(4, DayPlan.plan((0..8).map { "$it" to "$it" }, emptyList()).size)
    }
}
