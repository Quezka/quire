"""Pay worked out like an Italian payslip: hourly and monthly jobs, INPS, IRPEF, 13th pay."""
from datetime import date, timedelta

import pytest

from quire.application.inputs import JobInput, ShiftInput
from quire.application.errors import ValidationError
from quire.domain import PayTerms, monthly_gross, year_payslips
from quire.domain.payroll import cuneo_rate, irpef_before_detrazioni, work_detrazione

from .conftest import TODAY  # Wednesday 23 Sep 2026


def italy(**fields) -> PayTerms:
    return PayTerms(tax_model="italy", **fields)


def monthly_year(terms: PayTerms, year: int):
    return year_payslips(terms, year, [monthly_gross(terms, year, m) for m in range(1, 13)])


CONTRACT = italy(pay_mode="monthly", monthly_pay=446.23, mensilities=13,
                 contract_start=date(2026, 9, 1), contract_end=date(2027, 2, 26))


def test_monthly_contract_with_tredicesima_paid_with_the_last_payslip():
    slips = {(s.year, s.month): s for y in (2026, 2027) for s in monthly_year(CONTRACT, y)
             if s.gross}
    assert [(k, s.gross, s.net) for k, s in slips.items()] == [
        ((2026, 9), 446.23, 405.22), ((2026, 10), 446.23, 405.22),
        ((2026, 11), 446.23, 405.22),
        ((2026, 12), 594.97, 540.29),  # + 4/12 of the tredicesima
        ((2027, 1), 446.23, 405.22),
        ((2027, 2), 488.73, 443.82),  # 26 of 28 days, + 2/12 of the tredicesima
    ]
    assert slips[(2026, 9)].contributions == 41.01 and slips[(2026, 9)].irpef == 0
    assert slips[(2026, 9)].tfr == 30.82  # 446.23 / 13.5, less 0.5%


def test_no_income_tax_below_the_no_tax_area():
    assert work_detrazione(8_500, 365, False) >= irpef_before_detrazioni(8_500) - 0.01
    slips = year_payslips(italy(pay_mode="monthly", monthly_pay=700, mensilities=12), 2026,
                          [(700.0, 0.0)] * 12)
    assert sum(s.irpef for s in slips) == 0


def test_income_tax_above_it_follows_the_brackets_and_detrazioni():
    slips = year_payslips(italy(pay_mode="monthly", monthly_pay=2000, mensilities=12), 2026,
                          [(2000.0, 0.0)] * 12)
    taxable = 24_000 - sum(s.contributions for s in slips)
    detrazione = 1_910 + 1_190 * (28_000 - taxable) / 13_000
    assert sum(s.irpef for s in slips) == pytest.approx(taxable * 0.23 - detrazione, abs=0.01)
    assert irpef_before_detrazioni(60_000) == pytest.approx(28_000 * .23 + 22_000 * .33
                                                            + 10_000 * .43)


def test_a_short_contract_gets_a_prorated_detrazione():
    full = work_detrazione(3_000, 365, True)
    assert work_detrazione(3_000, 73, True) == pytest.approx(full / 5)
    assert work_detrazione(0, 100, True) == 0 and work_detrazione(3_000, 0, True) == 0


def test_surtax_is_only_due_once_irpef_is():
    base = dict(pay_mode="monthly", monthly_pay=2000, mensilities=12, addizionali=2.0)
    taxed = year_payslips(italy(**base), 2026, [(2000.0, 0.0)] * 12)
    assert sum(s.addizionali for s in taxed) > 0
    low = year_payslips(italy(**{**base, "monthly_pay": 500}), 2026, [(500.0, 0.0)] * 12)
    assert sum(s.addizionali for s in low) == 0


def test_cuneo_bonus_is_optional_and_depends_on_income():
    assert (cuneo_rate(8_000), cuneo_rate(12_000), cuneo_rate(18_000), cuneo_rate(30_000)) == (
        0.071, 0.053, 0.048, 0.0)
    base = dict(pay_mode="monthly", monthly_pay=446.23, mensilities=12)
    off = year_payslips(italy(**base), 2026, [(446.23, 0.0)] * 12)
    on = year_payslips(italy(**base, cuneo=True), 2026, [(446.23, 0.0)] * 12)
    assert sum(s.bonus for s in off) == 0
    assert sum(s.net for s in on) > sum(s.net for s in off)


def test_quattordicesima_is_paid_in_june():
    terms = italy(pay_mode="monthly", monthly_pay=1000, mensilities=14)
    slips = monthly_year(terms, 2026)
    assert slips[5].extra == 1000 and slips[11].extra == 1000
    assert sum(s.extra for s in slips) == 2000


def test_only_whole_enough_months_count_towards_the_tredicesima():
    terms = italy(pay_mode="monthly", monthly_pay=1200, mensilities=13,
                  contract_start=date(2026, 10, 20), contract_end=date(2026, 12, 31))
    slips = monthly_year(terms, 2026)
    assert slips[9].regular == round(1200 * 12 / 31, 2)  # 12 days of October
    assert slips[11].extra == 200  # only November and December count: 2/12


def test_flat_model_withholds_a_plain_percentage():
    slips = year_payslips(PayTerms(deductions=20.0), 2026, [(100.0, 0.0)] + [(0.0, 0.0)] * 11)
    assert (slips[0].contributions, slips[0].irpef, slips[0].net) == (20.0, 0, 80.0)


def test_payslips_add_up_to_the_year_to_the_cent():
    terms = italy(pay_mode="monthly", monthly_pay=1733.33, mensilities=13, addizionali=1.73)
    slips = monthly_year(terms, 2026)
    assert sum(s.irpef for s in slips) == pytest.approx(round(sum(s.irpef for s in slips), 2))
    assert round(sum(s.gross for s in slips), 2) == round(1733.33 * 13, 2)


# ---- through the use cases ------------------------------------------------------------

def job_with_contract(services, **fields):
    data = dict(pay_mode="monthly", monthly_pay=446.23, mensilities=13, tax_model="italy",
                contract_start=TODAY.replace(day=1), contract_end=TODAY.replace(day=1) + timedelta(days=88))
    data.update(fields)
    return services.work.save_job(None, JobInput("Office", **data))


def test_monthly_job_pays_in_the_month_summary_without_any_shift(services):
    job_id = job_with_contract(services, contract_start=None, contract_end=None)
    month = services.work.month_summary()
    assert (month.pay, month.net) == (446.23, 405.22)
    assert services.work.job(job_id).pay_mode == "monthly"


def test_a_week_of_a_monthly_job_is_its_share_of_the_month(services):
    job_with_contract(services, contract_start=None, contract_end=None)
    week = services.work.summary(date(2026, 9, 7), date(2026, 9, 13))
    assert week.pay == round(446.23 * 7 / 30, 2)


def test_payslips_list_only_months_that_pay(services):
    job_id = job_with_contract(services, contract_start=date(2026, 9, 1),
                               contract_end=date(2027, 2, 26))
    slips = services.work.payslips(job_id, 2026)
    assert [(s.month, s.gross, s.net) for s in slips] == [
        (9, 446.23, 405.22), (10, 446.23, 405.22), (11, 446.23, 405.22), (12, 594.97, 540.29)]
    assert services.work.payslips(job_id, 2025) == []


def test_hourly_job_net_follows_the_italian_rules(services):
    job_id = services.work.save_job(None, JobInput("Shop", hourly_rate=10.30, tax_model="italy"))
    services.work.save_shift(None, ShiftInput(job_id, TODAY, 16 * 60, 18 * 60))
    week = services.work.week_summary()
    assert (week.pay, week.net) == (20.6, round(20.6 * (1 - 0.0919), 2))
    assert [(p.gross, p.net) for p in services.work.payslips(job_id, TODAY.year)] == [
        (20.6, round(20.6 * (1 - 0.0919), 2))]


def test_a_monthly_job_ignores_the_hourly_rate_of_its_shifts(services):
    job_id = job_with_contract(services, hourly_rate=50.0, contract_start=None,
                               contract_end=None)
    services.work.save_shift(None, ShiftInput(job_id, TODAY, 16 * 60, 18 * 60))
    assert services.work.week_summary().minutes == 120
    assert services.work.preview(ShiftInput(job_id, TODAY, 16 * 60, 18 * 60)).pay is None


def test_job_pay_settings_round_trip(services):
    job_id = job_with_contract(services, addizionali=1.5, cuneo=True,
                               contract_start=date(2026, 9, 1), contract_end=date(2027, 2, 26))
    job = services.work.job(job_id)
    assert (job.mensilities, job.tax_model, job.addizionali, job.cuneo, job.inps) == (
        13, "italy", 1.5, True, 9.19)
    assert (job.contract_start, job.contract_end) == (date(2026, 9, 1), date(2027, 2, 26))


@pytest.mark.parametrize("bad", [dict(mensilities=15), dict(pay_mode="weekly"),
                                 dict(tax_model="x"), dict(monthly_pay=-1), dict(inps=100),
                                 dict(contract_start=date(2027, 1, 1),
                                      contract_end=date(2026, 1, 1))])
def test_invalid_pay_settings_are_refused(services, bad):
    with pytest.raises(ValidationError):
        services.work.save_job(None, JobInput("x", **bad))
