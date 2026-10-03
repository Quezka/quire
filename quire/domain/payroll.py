"""Italian employee payslips: gross pay, INPS, IRPEF with detrazioni, tredicesima and TFR.

Pure rules, no I/O. The phone mirrors them in `domain/Payroll.kt`; keep both in step
(`tests/test_payroll.py`, `PayrollTest`). Figures are estimates: the real payslip also
depends on other income, family detrazioni and local rules.

A year is worked out as a whole, then spread over its months by taxable pay, like the
employer's year-end conguaglio does.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

PAY_MODES = ("hourly", "monthly")
TAX_MODELS = ("italy", "flat")

BRACKETS = ((28_000.0, 0.23), (50_000.0, 0.33), (float("inf"), 0.43))  # IRPEF 2026
TFR_DIVISOR = 13.5
TFR_FUND_SHARE = 0.005  # withheld from the TFR quota for the INPS guarantee fund
# Cuneo fiscale bonus (income-dependent share of taxable pay), up to a 20,000 income.
CUNEO = ((8_500.0, 0.071), (15_000.0, 0.053), (20_000.0, 0.048))


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


@dataclass(frozen=True)
class PayTerms:
    """What a job pays and how it's taxed (the pay part of a Job)."""

    pay_mode: str = "hourly"
    monthly_pay: float | None = None  # gross per mensilità
    mensilities: int = 13  # 12, 13 or 14
    contract_start: date | None = None
    contract_end: date | None = None
    tax_model: str = "flat"
    deductions: float = 0.0  # flat model: percent withheld
    inps: float = 9.19  # italy model: employee contributions, percent
    addizionali: float = 0.0  # italy model: regional + municipal surtax, percent
    fixed_term: bool = True
    cuneo: bool = False

    @property
    def default_ratio(self) -> float:
        """Take-home share before any income tax: what's left after the contributions."""
        rate = self.inps if self.tax_model == "italy" else self.deductions
        return 1 - rate / 100


@dataclass(frozen=True)
class Payslip:
    """One calendar month of one job."""

    year: int
    month: int
    gross: float
    regular: float  # the part of gross that isn't tredicesima/quattordicesima
    contributions: float  # INPS, or the flat percentage
    irpef: float = 0.0
    addizionali: float = 0.0
    bonus: float = 0.0
    tfr: float = 0.0  # set aside for the severance pay, not part of net

    @property
    def net(self) -> float:
        return round2(self.gross - self.contributions - self.irpef - self.addizionali
                      + self.bonus)

    @property
    def extra(self) -> float:
        return round2(self.gross - self.regular)

    @property
    def ratio(self) -> float | None:
        """Share of gross that is take-home, or None for an unpaid month."""
        return self.net / self.gross if self.gross > 0 else None


def month_days(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def contract_days(terms: PayTerms, year: int, month: int) -> int:
    """Days of the month inside the contract (the whole month when it has no dates)."""
    first, last = date(year, month, 1), date(year, month, month_days(year, month))
    start = max(first, terms.contract_start) if terms.contract_start else first
    end = min(last, terms.contract_end) if terms.contract_end else last
    return max(0, (end - start).days + 1)


def employed(terms: PayTerms, year: int, month: int) -> bool:
    """A month counts towards tredicesima when at least 15 days of it are worked."""
    return contract_days(terms, year, month) >= 15


def _monthly_regular(terms: PayTerms, year: int, month: int) -> float:
    if terms.monthly_pay is None:
        return 0.0
    return round2(terms.monthly_pay * contract_days(terms, year, month)
                  / month_days(year, month))


def _months_between(terms: PayTerms, start: date, end_year: int, end_month: int) -> int:
    count, year, month = 0, start.year, start.month
    while (year, month) <= (end_year, end_month):
        count += employed(terms, year, month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return count


def _extra_pay(terms: PayTerms, year: int, month: int) -> float:
    """Tredicesima (paid in December) and quattordicesima (paid in June), pro rata.

    When the contract ends, whatever has built up is paid with the last payslip.
    """
    if terms.monthly_pay is None or terms.mensilities <= 12:
        return 0.0
    here = (year, month)
    if terms.contract_end and here > (terms.contract_end.year, terms.contract_end.month):
        return 0.0
    if terms.contract_start and here < (terms.contract_start.year, terms.contract_start.month):
        return 0.0
    ends = terms.contract_end is not None and (terms.contract_end.year,
                                               terms.contract_end.month) == here
    total = 0.0
    if month == 12 or ends:
        total += terms.monthly_pay * _months_between(terms, date(year, 1, 1), year, month) / 12
    if terms.mensilities >= 14 and (month == 6 or ends):
        start = date(year - 1, 7, 1) if month <= 6 else date(year, 7, 1)
        total += terms.monthly_pay * _months_between(terms, start, year, month) / 12
    return round2(total)


def monthly_gross(terms: PayTerms, year: int, month: int) -> tuple[float, float]:
    """(regular, extra) gross of a month for a job paid by the month."""
    return _monthly_regular(terms, year, month), _extra_pay(terms, year, month)


def employment_days(terms: PayTerms, year: int, worked: list[date] | None = None) -> int:
    """Days of the year the job lasted: what the work detrazione is prorated by."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    if terms.contract_start or terms.contract_end:
        start = max(first, terms.contract_start) if terms.contract_start else first
        end = min(last, terms.contract_end) if terms.contract_end else last
    elif terms.pay_mode == "hourly":
        days = sorted(d for d in (worked or []) if d.year == year)
        if not days:
            return 0
        start, end = days[0], days[-1]
    else:
        start, end = first, last
    return max(0, (end - start).days + 1)


def irpef_before_detrazioni(taxable: float) -> float:
    tax, floor = 0.0, 0.0
    for ceiling, rate in BRACKETS:
        if taxable > floor:
            tax += (min(taxable, ceiling) - floor) * rate
        floor = ceiling
    return tax


def work_detrazione(taxable: float, days: int, fixed_term: bool) -> float:
    """Detrazione for employees, prorated by the days worked in the year."""
    if taxable <= 0 or days <= 0:
        return 0.0
    if taxable <= 15_000:
        full = 1_955.0
    elif taxable <= 28_000:
        full = 1_910 + 1_190 * (28_000 - taxable) / 13_000
    elif taxable <= 50_000:
        full = 1_910 * (50_000 - taxable) / 22_000
    else:
        full = 0.0
    if 25_000 < taxable <= 35_000:
        full += 65
    if taxable <= 15_000:
        full = max(full, 690.0 if fixed_term else 1_380.0)
    return full * min(days, 365) / 365


def cuneo_rate(taxable: float) -> float:
    return next((rate for ceiling, rate in CUNEO if taxable <= ceiling), 0.0)


def _spread(total: float, weights: list[float]) -> list[float]:
    """Split `total` in proportion to `weights`, to the cent, summing back exactly."""
    whole = sum(weights)
    if total == 0 or whole <= 0:
        return [0.0] * len(weights)
    parts = [round2(total * w / whole) for w in weights]
    last = max(i for i, w in enumerate(weights) if w > 0)
    parts[last] = round2(parts[last] + total - sum(parts))
    return parts


def year_payslips(terms: PayTerms, year: int, grosses: list[tuple[float, float]],
                  worked: list[date] | None = None) -> list[Payslip]:
    """The twelve payslips of `year`.

    `grosses` is (regular, extra) gross pay for each month: hours times the rate for an
    hourly job, `monthly_gross()` for a monthly one. `worked` are the days with shifts,
    used to date an hourly job that has no contract dates.
    """
    gross = [round2(r + e) for r, e in grosses]
    rate = terms.inps if terms.tax_model == "italy" else terms.deductions
    contributions = [round2(g * rate / 100) for g in gross]
    irpef = [0.0] * 12
    addizionali = [0.0] * 12
    bonus = [0.0] * 12
    if terms.tax_model == "italy" and sum(gross) > 0:
        taxable = [g - c for g, c in zip(gross, contributions)]
        income = sum(taxable)
        days = employment_days(terms, year, worked)
        due = max(0.0, irpef_before_detrazioni(income)
                  - work_detrazione(income, days, terms.fixed_term))
        due = round2(due)
        irpef = _spread(due, taxable)
        if due > 0:
            addizionali = _spread(round2(income * terms.addizionali / 100), taxable)
        if terms.cuneo:
            bonus = _spread(round2(income * cuneo_rate(income)), taxable)
    return [Payslip(year, m + 1, gross[m], round2(grosses[m][0]), contributions[m],
                    irpef[m], addizionali[m], bonus[m],
                    round2(gross[m] / TFR_DIVISOR - gross[m] * TFR_FUND_SHARE))
            for m in range(12)]


def take_home(terms: PayTerms, slip: Payslip, gross: float) -> float:
    """Net of `gross` earned in the month of `slip`, at that month's take-home share."""
    ratio = slip.ratio
    return round2(gross * (terms.default_ratio if ratio is None else ratio))


def monthly_share(terms: PayTerms, slip: Payslip, first: date, last: date) -> tuple[float, float]:
    """(gross, net) of a monthly job's payslip that falls inside first..last.

    The regular pay counts by the contract days in the range; tredicesima and
    quattordicesima count when the range holds the month's last contract day.
    """
    year, month = slip.year, slip.month
    start, end = date(year, month, 1), date(year, month, month_days(year, month))
    if terms.contract_start:
        start = max(start, terms.contract_start)
    if terms.contract_end:
        end = min(end, terms.contract_end)
    if start > end or slip.gross <= 0:
        return 0.0, 0.0
    lo, hi = max(start, first), min(end, last)
    days = max(0, (hi - lo).days + 1)
    gross = slip.regular * days / ((end - start).days + 1)
    if first <= end <= last:
        gross += slip.extra
    if gross <= 0:
        return 0.0, 0.0
    return round2(gross), round2(slip.net * gross / slip.gross)
