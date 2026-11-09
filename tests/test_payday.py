"""Payday: a job's take-home pay goes into Money by itself, once per month, on every device."""
from datetime import date

from quire.application.inputs import JobInput, TransactionInput
from quire.domain.payroll import due_paydays
from quire.infrastructure.credentials import MemoryCredentialStore
from quire.bootstrap import build_services

from .conftest import FixedClock
from .fakes import FakeDiagrams, FakeRegister
from .test_sync import connect, shared_cloud  # noqa: F401 (fixture)


def test_due_paydays_from_switch_on_with_short_months():
    assert due_paydays(None, True, date(2026, 1, 1), date(2026, 6, 1)) == []
    # Switched on 5 Jan: the 31st falls on the month's last day; nothing before the switch.
    got = due_paydays(31, True, date(2026, 1, 5), date(2026, 3, 30))
    assert got == [(date(2026, 1, 31), 2025, 12), (date(2026, 2, 28), 2026, 1)]
    assert due_paydays(10, False, date(2026, 1, 11), date(2026, 2, 10)) == [(date(2026, 2, 10), 2026, 2)]


def _job(services, payday=10, previous=True):
    return services.work.save_job(None, JobInput("Bar", pay_mode="monthly", monthly_pay=1200.0, mensilities=12,
                                                 payday=payday, pays_previous_month=previous))


def _income(services, year, month):
    return [t for t in services.finance.month(year, month).transactions if t.income]


def test_pay_is_booked_once_and_a_deleted_one_stays_deleted(tmp_path):
    clock = FixedClock(date(2026, 9, 5))
    services, db = build_services(tmp_path / "q.db", clock, FakeRegister(), MemoryCredentialStore(),
                                  diagrams=FakeDiagrams())
    _job(services)
    assert services.work.book_pay() == 0  # switched on the 5th: September's payday is still ahead
    clock._today = date(2026, 9, 10)
    assert services.work.book_pay() == 1
    assert services.work.book_pay() == 0
    (entry,) = _income(services, 2026, 9)
    assert entry.day == date(2026, 9, 10) and entry.cents > 0 and "08/2026" in entry.note
    services.finance.delete(entry.id)
    assert services.work.book_pay() == 0
    clock._today = date(2026, 11, 12)
    assert services.work.book_pay() == 2  # October and November, after a while away
    db.close()


def test_two_devices_make_one_entry(tmp_path, shared_cloud):
    devices = []
    for name in ("laptop", "desktop"):
        clock = FixedClock(date(2026, 9, 1))
        s, db = build_services(tmp_path / f"{name}.db", clock, FakeRegister(), MemoryCredentialStore(),
                               shared_cloud, MemoryCredentialStore(), diagrams=FakeDiagrams())
        devices.append((s, db, clock))
    (a, db_a, clock_a), (b, db_b, clock_b) = devices
    connect(a, create=True)
    connect(b)
    _job(a)
    a.sync.sync()
    b.sync.sync()
    clock_a._today = clock_b._today = date(2026, 9, 10)
    assert a.work.book_pay() == 1 and b.work.book_pay() == 1  # neither has heard from the other yet
    a.sync.sync()
    b.sync.sync()
    a.sync.sync()
    assert len(_income(a, 2026, 9)) == 1 and len(_income(b, 2026, 9)) == 1
    db_a.close()
    db_b.close()
