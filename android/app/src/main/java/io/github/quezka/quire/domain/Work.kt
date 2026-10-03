package io.github.quezka.quire.domain

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.TemporalAdjusters
import kotlin.math.roundToLong

/** Pay and schedules for jobs, with the desktop's rules (domain/model.py, services/work.py). */

val Shift.paidMinutes get() = duration - breakMinutes
val Shift.endsNextDay get() = end > MINUTES_PER_DAY

fun round2(value: Double) = (value * 100).roundToLong() / 100.0

fun Shift.pay(hourlyRate: Double?): Double? = hourlyRate?.let { round2(paidMinutes / 60.0 * it) }

/** Take-home pay once [deductions] percent is withheld. */
fun netPay(gross: Double?, deductions: Double): Double? = gross?.let { round2(it * (1 - deductions / 100)) }

/** What a shift pays: only a job paid by the hour pays by the shift. */
fun Shift.pay(job: Job?): Double? = if (job == null || job.payMode != "hourly") null else pay(job.hourlyRate)

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

    /** The twelve payslips of [year] for a job (worked out from its shifts when paid by the hour). */
    fun slips(job: Job, year: Int, oneOff: List<Shift>): List<Payslip> {
        val terms = job.terms
        if (terms.payMode == "monthly") {
            return Payroll.yearPayslips(terms, year, (1..12).map { Payroll.monthlyGross(terms, year, it) })
        }
        val shifts = Agenda.shifts(listOf(job), oneOff.filter { it.jobUid == job.uid },
            LocalDate.of(year, 1, 1), LocalDate.of(year, 12, 31)).filter { it.day.year == year }
        val totals = DoubleArray(12)
        for (s in shifts) totals[s.day.monthValue - 1] += s.pay(job.hourlyRate) ?: 0.0
        return Payroll.yearPayslips(terms, year, totals.map { round2(it) to 0.0 }, shifts.map { it.day })
    }

    /** The months of [year] in which the job pays something. */
    fun payslips(job: Job, year: Int, oneOff: List<Shift>) = slips(job, year, oneOff).filter { it.gross > 0 }

    /** Take-home pay of a shift's [gross], at the take-home share of its month. */
    fun shiftNet(job: Job, shift: Shift, gross: Double, oneOff: List<Shift>) =
        Payroll.takeHome(job.terms, slips(job, shift.day.year, oneOff)[shift.day.monthValue - 1], gross)

    private fun jobPay(job: Job, shifts: List<Shift>, first: LocalDate, last: LocalDate, oneOff: List<Shift>,
                       cache: MutableMap<Pair<String, Int>, List<Payslip>>): Pair<Double?, Double?> {
        fun slipsOf(year: Int) = cache.getOrPut(job.uid to year) { slips(job, year, oneOff) }
        val terms = job.terms
        if (terms.payMode == "monthly") {
            if (terms.monthlyPay == null) return null to null
            var gross = 0.0; var net = 0.0
            var month = YearMonth.from(first)
            while (!month.isAfter(YearMonth.from(last))) {
                val (g, n) = Payroll.monthlyShare(terms, slipsOf(month.year)[month.monthValue - 1], first, last)
                gross += g; net += n
                month = month.plusMonths(1)
            }
            return round2(gross) to round2(net)
        }
        val pays = shifts.map { it.pay(job.hourlyRate) }
        if (pays.any { it == null }) return null to null
        val byMonth = LinkedHashMap<Pair<Int, Int>, Double>()
        shifts.forEachIndexed { i, s ->
            val key = s.day.year to s.day.monthValue
            byMonth[key] = (byMonth[key] ?: 0.0) + pays[i]!!
        }
        val net = byMonth.entries.sumOf { (key, g) -> Payroll.takeHome(terms, slipsOf(key.first)[key.second - 1], g) }
        return round2(byMonth.values.sum()) to round2(net)
    }

    fun summary(jobs: List<Job>, oneOff: List<Shift>, first: LocalDate, last: LocalDate): WorkSummary {
        val byUid = jobs.associateBy { it.uid }
        val shifts = Agenda.shifts(jobs, oneOff, first, last)
        val grouped = shifts.groupBy { it.jobUid }.toMutableMap()
        // A monthly job is paid even in a week without shifts.
        for (job in jobs) if (job.payMode == "monthly" && job.monthlyPay != null) grouped.getOrPut(job.uid) { emptyList() }
        val cache = mutableMapOf<Pair<String, Int>, List<Payslip>>()
        val totals = grouped.map { (jobUid, list) ->
            val job = byUid[jobUid]
            val (gross, net) = if (job == null) null to null else jobPay(job, list, first, last, oneOff, cache)
            JobTotal(job, list.sumOf { it.paidMinutes }, gross, net)
        }.filter { it.minutes > 0 || (it.pay ?: 0.0) > 0 }
            .sortedBy { it.job?.name?.lowercase().orEmpty() }
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
