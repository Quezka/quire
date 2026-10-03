package io.github.quezka.quire.domain

import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.ChronoUnit
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToLong

/**
 * Italian employee payslips: gross pay, INPS, IRPEF with detrazioni, tredicesima and TFR.
 * The desktop's rules (domain/payroll.py), line for line: keep both in step
 * (`PayrollTest`, `tests/test_payroll.py`). Figures are estimates.
 */

private fun cents(value: Double) = ((value + 1e-9) * 100).roundToLong() / 100.0

data class PayTerms(
    val payMode: String = "hourly",
    val monthlyPay: Double? = null, // gross per mensilità
    val mensilities: Int = 13,
    val contractStart: LocalDate? = null,
    val contractEnd: LocalDate? = null,
    val taxModel: String = "flat",
    val deductions: Double = 0.0, // flat model: percent withheld
    val inps: Double = 9.19,
    val addizionali: Double = 0.0,
    val fixedTerm: Boolean = true,
    val cuneo: Boolean = false,
) {
    /** Take-home share before any income tax. */
    val defaultRatio get() = 1 - (if (taxModel == "italy") inps else deductions) / 100
}

data class Payslip(
    val year: Int,
    val month: Int,
    val gross: Double,
    val regular: Double, // gross without tredicesima / quattordicesima
    val contributions: Double,
    val irpef: Double = 0.0,
    val addizionali: Double = 0.0,
    val bonus: Double = 0.0,
    val tfr: Double = 0.0,
) {
    val net get() = cents(gross - contributions - irpef - addizionali + bonus)
    val extra get() = cents(gross - regular)
    val ratio: Double? get() = if (gross > 0) net / gross else null
}

object Payroll {
    private val BRACKETS = listOf(28_000.0 to 0.23, 50_000.0 to 0.33, Double.POSITIVE_INFINITY to 0.43)
    private const val TFR_DIVISOR = 13.5
    private const val TFR_FUND_SHARE = 0.005
    private val CUNEO = listOf(8_500.0 to 0.071, 15_000.0 to 0.053, 20_000.0 to 0.048)

    fun monthDays(year: Int, month: Int) = YearMonth.of(year, month).lengthOfMonth()

    private fun days(from: LocalDate, to: LocalDate) = ChronoUnit.DAYS.between(from, to).toInt()

    /** Days of the month inside the contract (the whole month when it has no dates). */
    fun contractDays(t: PayTerms, year: Int, month: Int): Int {
        val first = LocalDate.of(year, month, 1)
        val last = LocalDate.of(year, month, monthDays(year, month))
        val start = t.contractStart?.let { maxOf(first, it) } ?: first
        val end = t.contractEnd?.let { minOf(last, it) } ?: last
        return max(0, days(start, end) + 1)
    }

    private fun employed(t: PayTerms, year: Int, month: Int) = contractDays(t, year, month) >= 15

    private fun monthlyRegular(t: PayTerms, year: Int, month: Int): Double {
        val pay = t.monthlyPay ?: return 0.0
        return cents(pay * contractDays(t, year, month) / monthDays(year, month))
    }

    private fun monthsBetween(t: PayTerms, start: LocalDate, endYear: Int, endMonth: Int): Int {
        var count = 0
        var ym = YearMonth.of(start.year, start.monthValue)
        val end = YearMonth.of(endYear, endMonth)
        while (!ym.isAfter(end)) {
            if (employed(t, ym.year, ym.monthValue)) count++
            ym = ym.plusMonths(1)
        }
        return count
    }

    /** Tredicesima (December) and quattordicesima (June), pro rata; the rest is paid when the contract ends. */
    private fun extraPay(t: PayTerms, year: Int, month: Int): Double {
        val pay = t.monthlyPay ?: return 0.0
        if (t.mensilities <= 12) return 0.0
        val here = YearMonth.of(year, month)
        t.contractEnd?.let { if (here.isAfter(YearMonth.of(it.year, it.monthValue))) return 0.0 }
        t.contractStart?.let { if (here.isBefore(YearMonth.of(it.year, it.monthValue))) return 0.0 }
        val ends = t.contractEnd?.let { YearMonth.of(it.year, it.monthValue) == here } ?: false
        var total = 0.0
        if (month == 12 || ends) total += pay * monthsBetween(t, LocalDate.of(year, 1, 1), year, month) / 12
        if (t.mensilities >= 14 && (month == 6 || ends)) {
            val start = if (month <= 6) LocalDate.of(year - 1, 7, 1) else LocalDate.of(year, 7, 1)
            total += pay * monthsBetween(t, start, year, month) / 12
        }
        return cents(total)
    }

    /** (regular, extra) gross of a month for a job paid by the month. */
    fun monthlyGross(t: PayTerms, year: Int, month: Int) = monthlyRegular(t, year, month) to extraPay(t, year, month)

    /** Days of the year the job lasted: what the work detrazione is prorated by. */
    fun employmentDays(t: PayTerms, year: Int, worked: List<LocalDate>? = null): Int {
        val first = LocalDate.of(year, 1, 1)
        val last = LocalDate.of(year, 12, 31)
        val start: LocalDate
        val end: LocalDate
        if (t.contractStart != null || t.contractEnd != null) {
            start = t.contractStart?.let { maxOf(first, it) } ?: first
            end = t.contractEnd?.let { minOf(last, it) } ?: last
        } else if (t.payMode == "hourly") {
            val inYear = (worked ?: emptyList()).filter { it.year == year }.sorted()
            if (inYear.isEmpty()) return 0
            start = inYear.first(); end = inYear.last()
        } else {
            start = first; end = last
        }
        return max(0, days(start, end) + 1)
    }

    fun irpefBeforeDetrazioni(taxable: Double): Double {
        var tax = 0.0
        var floor = 0.0
        for ((ceiling, rate) in BRACKETS) {
            if (taxable > floor) tax += (min(taxable, ceiling) - floor) * rate
            floor = ceiling
        }
        return tax
    }

    /** Detrazione for employees, prorated by the days worked in the year. */
    fun workDetrazione(taxable: Double, days: Int, fixedTerm: Boolean): Double {
        if (taxable <= 0 || days <= 0) return 0.0
        var full = when {
            taxable <= 15_000 -> 1_955.0
            taxable <= 28_000 -> 1_910 + 1_190 * (28_000 - taxable) / 13_000
            taxable <= 50_000 -> 1_910 * (50_000 - taxable) / 22_000
            else -> 0.0
        }
        if (taxable > 25_000 && taxable <= 35_000) full += 65
        if (taxable <= 15_000) full = max(full, if (fixedTerm) 690.0 else 1_380.0)
        return full * min(days, 365) / 365
    }

    fun cuneoRate(taxable: Double) = CUNEO.firstOrNull { taxable <= it.first }?.second ?: 0.0

    /** Split [total] in proportion to [weights], to the cent, summing back exactly. */
    private fun spread(total: Double, weights: List<Double>): List<Double> {
        val whole = weights.sum()
        if (total == 0.0 || whole <= 0) return List(weights.size) { 0.0 }
        val parts = weights.map { cents(total * it / whole) }.toMutableList()
        val last = weights.indices.last { weights[it] > 0 }
        parts[last] = cents(parts[last] + total - parts.sum())
        return parts
    }

    /** The twelve payslips of [year]; [grosses] is (regular, extra) gross for each month. */
    fun yearPayslips(t: PayTerms, year: Int, grosses: List<Pair<Double, Double>>, worked: List<LocalDate>? = null): List<Payslip> {
        val gross = grosses.map { cents(it.first + it.second) }
        val rate = if (t.taxModel == "italy") t.inps else t.deductions
        val contributions = gross.map { cents(it * rate / 100) }
        var irpef = List(12) { 0.0 }
        var addizionali = List(12) { 0.0 }
        var bonus = List(12) { 0.0 }
        if (t.taxModel == "italy" && gross.sum() > 0) {
            val taxable = gross.zip(contributions) { g, c -> g - c }
            val income = taxable.sum()
            val employed = employmentDays(t, year, worked)
            val due = cents(max(0.0, irpefBeforeDetrazioni(income) - workDetrazione(income, employed, t.fixedTerm)))
            irpef = spread(due, taxable)
            if (due > 0) addizionali = spread(cents(income * t.addizionali / 100), taxable)
            if (t.cuneo) bonus = spread(cents(income * cuneoRate(income)), taxable)
        }
        return List(12) { m ->
            Payslip(year, m + 1, gross[m], cents(grosses[m].first), contributions[m], irpef[m], addizionali[m],
                bonus[m], cents(gross[m] / TFR_DIVISOR - gross[m] * TFR_FUND_SHARE))
        }
    }

    /** Net of [gross] earned in the month of [slip], at that month's take-home share. */
    fun takeHome(t: PayTerms, slip: Payslip, gross: Double) = cents(gross * (slip.ratio ?: t.defaultRatio))

    /** (gross, net) of a monthly job's payslip that falls inside [first]..[last]. */
    fun monthlyShare(t: PayTerms, slip: Payslip, first: LocalDate, last: LocalDate): Pair<Double, Double> {
        var start = LocalDate.of(slip.year, slip.month, 1)
        var end = LocalDate.of(slip.year, slip.month, monthDays(slip.year, slip.month))
        t.contractStart?.let { start = maxOf(start, it) }
        t.contractEnd?.let { end = minOf(end, it) }
        if (start.isAfter(end) || slip.gross <= 0) return 0.0 to 0.0
        val lo = maxOf(start, first)
        val hi = minOf(end, last)
        val shared = max(0, days(lo, hi) + 1)
        var gross = slip.regular * shared / (days(start, end) + 1)
        if (!first.isAfter(end) && !end.isAfter(last)) gross += slip.extra
        if (gross <= 0) return 0.0 to 0.0
        return cents(gross) to cents(slip.net * gross / slip.gross)
    }
}
