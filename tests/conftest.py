from datetime import date, datetime

import pytest

from quire.bootstrap import build_services

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
def services(clock):
    services, db = build_services(":memory:", clock)
    yield services
    db.close()
