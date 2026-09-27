from datetime import date, datetime

import pytest

from quire.bootstrap import build_services
from quire.infrastructure.credentials import MemoryCredentialStore

from .fakes import FakeCloud, FakeInstaller, FakeRegister, FakeReleases

# A Wednesday.
TODAY = date(2026, 9, 23)


class FixedClock:
    def __init__(self, today: date = TODAY):
        self._today = today

    def today(self) -> date:
        return self._today

    def now(self) -> datetime:
        return datetime.combine(self._today, datetime.min.time()).replace(hour=12)


@pytest.fixture
def clock():
    return FixedClock()


@pytest.fixture
def register():
    return FakeRegister()


@pytest.fixture
def credentials():
    return MemoryCredentialStore()


@pytest.fixture
def cloud():
    return FakeCloud()


@pytest.fixture
def releases():
    return FakeReleases()


@pytest.fixture
def installer():
    return FakeInstaller()


@pytest.fixture
def services(clock, register, credentials, cloud, releases, installer):
    services, db = build_services(":memory:", clock, register, credentials, cloud,
                                  MemoryCredentialStore(), releases, installer)
    yield services
    db.close()
