import os
from datetime import date, datetime

import pytest

os.environ.setdefault("QT_SCALE_FACTOR", "1")  # tests measure pixels: no automatic scaling

from quire.bootstrap import build_services
from quire.infrastructure.credentials import MemoryCredentialStore

from .fakes import (
    FakeCloud, FakeDiagrams, FakeInstaller, FakeLoginItem, FakeRegister, FakeReleases,
)

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
def login_item():
    return FakeLoginItem()


@pytest.fixture
def diagrams():
    return FakeDiagrams()


@pytest.fixture
def services(clock, register, credentials, cloud, releases, installer, login_item, diagrams):
    services, db = build_services(":memory:", clock, register, credentials, cloud,
                                  MemoryCredentialStore(), releases, installer, login_item,
                                  diagrams)
    yield services
    db.close()


@pytest.fixture(autouse=True)
def full_hd_screen(monkeypatch):
    """The headless test screen is tiny; windows are clamped to the screen, so pretend it is
    a normal one (the clamp itself is tested in test_uiscale)."""
    try:
        from PySide6.QtCore import QRect
        from quire.presentation import fit
    except ImportError:
        return
    monkeypatch.setattr(fit, "available", lambda widget=None: QRect(0, 0, 1920, 1040))
