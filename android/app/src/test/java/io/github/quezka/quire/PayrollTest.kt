package io.github.quezka.quire

import io.github.quezka.quire.domain.Job
import io.github.quezka.quire.domain.Payroll
import io.github.quezka.quire.domain.PayTerms
import io.github.quezka.quire.domain.Shift
import io.github.quezka.quire.domain.Work
import io.github.quezka.quire.domain.pay
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/** The same cases as the desktop's tests/test_payroll.py: both sides must agree to the cent. */
class PayrollTest {
    private val contract = PayTerms(
        payMode = "monthly", monthlyPay = 446.23, mensilities = 13, taxModel = "italy",
        contractStart = LocalDate.of(2026, 9, 1), contractEnd = LocalDate.of(2027, 2, 26))

    private fun year(t: PayTerms, y: Int) =
        Payroll.yearPayslips(t, y, (1..12).map { Payroll.monthlyGross(t, y, it) })

    @Test fun monthlyContractWithTredicesimaPaidWithTheLastPayslip() {
        val slips = (year(contract, 2026) + year(contract, 2027)).filter { it.gross > 0 }
        assertEquals(listOf(
            Triple(9, 446.23, 405.22), Triple(10, 446.23, 405.22), Triple(11, 446.23, 405.22),
            Triple(12, 594.97, 540.29), Triple(1, 446.23, 405.22), Triple(2, 488.73, 443.82),
        ), slips.map { Triple(it.month, it.gross, it.net) })
        assertEquals(41.01, slips[0].contributions, 0.0)
        assertEquals(0.0, slips[0].irpef, 0.0)
        assertEquals(30.82, slips[0].tfr, 0.0)
    }

    @Test fun noIncomeTaxBelowTheNoTaxArea() {
        val t = PayTerms("monthly", 700.0, 12, taxModel = "italy")
        assertEquals(0.0, Payroll.yearPayslips(t, 2026, List(12) { 700.0 to 0.0 }).sumOf { it.irpef }, 0.0)
    }

    @Test fun incomeTaxAboveItFollowsBracketsAndDetrazioni() {
        val t = PayTerms("monthly", 2000.0, 12, taxModel = "italy")
        val slips = Payroll.yearPayslips(t, 2026, List(12) { 2000.0 to 0.0 })
        val taxable = 24_000 - slips.sumOf { it.contributions }
        val detrazione = 1_910 + 1_190 * (28_000 - taxable) / 13_000
        assertEquals(taxable * 0.23 - detrazione, slips.sumOf { it.irpef }, 0.01)
        assertEquals(28_000 * .23 + 22_000 * .33 + 10_000 * .43, Payroll.irpefBeforeDetrazioni(60_000.0), 0.001)
    }

    @Test fun shortContractGetsAProratedDetrazione() {
        assertEquals(Payroll.workDetrazione(3_000.0, 365, true) / 5, Payroll.workDetrazione(3_000.0, 73, true), 0.001)
        assertEquals(0.0, Payroll.workDetrazione(0.0, 100, true), 0.0)
    }

    @Test fun surtaxAndCuneoBonus() {
        val base = PayTerms("monthly", 2000.0, 12, taxModel = "italy", addizionali = 2.0)
        assertTrue(Payroll.yearPayslips(base, 2026, List(12) { 2000.0 to 0.0 }).sumOf { it.addizionali } > 0)
        val low = base.copy(monthlyPay = 500.0)
        assertEquals(0.0, Payroll.yearPayslips(low, 2026, List(12) { 500.0 to 0.0 }).sumOf { it.addizionali }, 0.0)
        assertEquals(listOf(0.071, 0.053, 0.048, 0.0), listOf(8_000.0, 12_000.0, 18_000.0, 30_000.0).map(Payroll::cuneoRate))
        val off = PayTerms("monthly", 446.23, 12, taxModel = "italy")
        val on = off.copy(cuneo = true)
        val g = List(12) { 446.23 to 0.0 }
        assertTrue(Payroll.yearPayslips(on, 2026, g).sumOf { it.net } > Payroll.yearPayslips(off, 2026, g).sumOf { it.net })
    }

    @Test fun quattordicesimaAndPartMonths() {
        val t = PayTerms("monthly", 1000.0, 14, taxModel = "italy")
        val slips = year(t, 2026)
        assertEquals(1000.0, slips[5].extra, 0.0)
        assertEquals(1000.0, slips[11].extra, 0.0)
        val late = PayTerms("monthly", 1200.0, 13, taxModel = "italy",
            contractStart = LocalDate.of(2026, 10, 20), contractEnd = LocalDate.of(2026, 12, 31))
        val s = year(late, 2026)
        assertEquals(Math.round(1200.0 * 12 / 31 * 100) / 100.0, s[9].regular, 0.0)
        assertEquals(200.0, s[11].extra, 0.0) // only November and December count
    }

    @Test fun flatModelWithholdsAPlainPercentage() {
        val s = Payroll.yearPayslips(PayTerms(deductions = 20.0), 2026, listOf(100.0 to 0.0) + List(11) { 0.0 to 0.0 })[0]
        assertEquals(80.0, s.net, 0.0)
        assertEquals(0.0, s.irpef, 0.0)
    }

    @Test fun summariesOfMonthlyAndHourlyJobs() {
        val monthly = Job("m", "Office", payMode = "monthly", monthlyPay = 446.23, taxModel = "italy")
        val month = Work.summary(listOf(monthly), emptyList(), LocalDate.of(2026, 9, 1), LocalDate.of(2026, 9, 30))
        assertEquals(446.23, month.pay!!, 0.0)
        assertEquals(405.22, month.net!!, 0.0)
        val week = Work.summary(listOf(monthly), emptyList(), LocalDate.of(2026, 9, 7), LocalDate.of(2026, 9, 13))
        assertEquals(Math.round(446.23 * 7 / 30 * 100) / 100.0, week.pay!!, 0.0)

        val hourly = Job("h", "Shop", hourlyRate = 10.30, taxModel = "italy")
        val shift = Shift(null, "h", LocalDate.of(2026, 9, 23), 16 * 60, 120)
        val result = Work.summary(listOf(hourly), listOf(shift.copy(uid = "s1")), LocalDate.of(2026, 9, 21), LocalDate.of(2026, 9, 27))
        assertEquals(20.6, result.pay!!, 0.0)
        assertEquals(Math.round(20.6 * (1 - 0.0919) * 100) / 100.0, result.net!!, 0.0)
        assertEquals(listOf(9), Work.payslips(hourly, 2026, listOf(shift.copy(uid = "s1"))).map { it.month })
    }

    @Test fun aMonthlyJobDoesNotPayByTheShift() {
        val job = Job("m", "Office", hourlyRate = 50.0, payMode = "monthly", monthlyPay = 400.0)
        assertNull(Shift("s", "m", LocalDate.of(2026, 9, 23), 960, 120).pay(job))
    }
}
