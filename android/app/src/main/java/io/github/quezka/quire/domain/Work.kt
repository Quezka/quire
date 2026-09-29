package io.github.quezka.quire.domain

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import kotlin.math.roundToLong

/** Pay and schedules for jobs, with the desktop's rules (domain/model.py, services/work.py). */

val Shift.paidMinutes get() = duration - breakMinutes
val Shift.endsNextDay get() = end > MINUTES_PER_DAY

fun round2(value: Double) = (value * 100).roundToLong() / 100.0

fun Shift.pay(hourlyRate: Double?): Double? = hourlyRate?.let { round2(paidMinutes / 60.0 * it) }

/** Take-home pay once [deductions] percent is withheld. */
fun netPay(gross: Double?, deductions: Double): Double? = gross?.let { round2(it * (1 - deductions / 100)) }

/** Minutes from [start] to [end], past midnight when [end] isn't after [start]. */
fun durationBetween(start: Int, end: Int) = if (end > start) end - start else end + MINUTES_PER_DAY - start

val ShiftPattern.key get() = listOf(weekday, start, duration, breakMinutes)

fun LocalDate.monday(): LocalDate = with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

data class JobTotal(val job: Job?, val minutes: Int, val pay: Double?, val net: Double?)

data class WorkSummary(
    val first: LocalDate,
    val last: LocalDate,
    val minutes: Int,
    val pay: Double?,
    val net: Double?,
    val shifts: Int,
    val totals: List<JobTotal>,
)

object Work {
    const val MAX_SHIFT_MINUTES = 24 * 60
    const val MAX_REPEAT_WEEKS = 52

    /** Why a shift can't be saved, or null. Messages match the desktop's. */
    fun problem(start: Int, duration: Int, breakMinutes: Int): String? = when {
        start !in 0 until MINUTES_PER_DAY -> "Start time must be within the day."
        duration <= 0 -> "A shift must last at least a minute."
        duration > MAX_SHIFT_MINUTES -> "A shift can't be longer than 24 hours."
        breakMinutes < 0 -> "A break can't be negative."
        breakMinutes >= duration -> "The break must be shorter than the shift."
        else -> null
    }

    fun summary(jobs: List<Job>, oneOff: List<Shift>, first: LocalDate, last: LocalDate): WorkSummary {
        val byUid = jobs.associateBy { it.uid }
        val shifts = Agenda.shifts(jobs, oneOff, first, last)
        val totals = shifts.groupBy { it.jobUid }.map { (jobUid, list) ->
            val job = byUid[jobUid]
            val pays = list.map { it.pay(job?.hourlyRate) }
            val unknown = pays.any { it == null }
            val gross = if (unknown) null else round2(pays.sumOf { it!! })
            JobTotal(job, list.sumOf { it.paidMinutes }, gross, netPay(gross, job?.deductions ?: 0.0))
        }.sortedBy { it.job?.name?.lowercase().orEmpty() }
        val gross = totals.mapNotNull { it.pay }
        val net = totals.mapNotNull { it.net }
        return WorkSummary(first, last, totals.sumOf { it.minutes },
            if (gross.isEmpty()) null else round2(gross.sum()),
            if (net.isEmpty()) null else round2(net.sum()), shifts.size, totals)
    }

    fun week(jobs: List<Job>, oneOff: List<Shift>, today: LocalDate): WorkSummary {
        val monday = today.monday()
        return summary(jobs, oneOff, monday, monday.plusDays(6))
    }

    fun month(jobs: List<Job>, oneOff: List<Shift>, today: LocalDate): WorkSummary {
        val first = today.withDayOfMonth(1)
        return summary(jobs, oneOff, first, first.plusMonths(1).minusDays(1))
    }

    /** The weekly schedule in use from [thisWeek] (a Monday): the desktop's `reschedule`.
     *  Unchanged patterns stay; dropped ones end the Sunday before (or vanish if they only
     *  started this week); new ones start this week. Ended patterns stay for history. */
    fun reschedule(current: List<ShiftPattern>, wanted: List<ShiftPattern>, thisWeek: LocalDate): List<ShiftPattern> {
        val active = current.filter { it.until == null || it.until >= thisWeek }
        val wantedKeys = wanted.map { it.key }.toSet()
        val activeKeys = active.map { it.key }.toMutableSet()
        val result = current.filter { it !in active }.toMutableList()
        for (p in active) {
            when {
                p.key in wantedKeys -> result += p
                p.since == null || p.since < thisWeek -> result += p.copy(until = thisWeek.minusDays(1))
            }
        }
        for (p in wanted) {
            if (activeKeys.add(p.key)) result += p.copy(since = thisWeek, until = null)
        }
        return result
    }

    /** The patterns in use today (what the schedule editor shows). */
    fun activeSchedule(job: Job, today: LocalDate) =
        job.patterns.filter { (it.until == null || it.until >= today) }
            .sortedWith(compareBy({ it.weekday }, { it.start }))
}
