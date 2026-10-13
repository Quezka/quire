"""The start-up splash: it paints, follows the start-up steps and goes away by itself."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402

from quire.presentation.qt_app import create_application  # noqa: E402
from quire.presentation.splash import SplashScreen  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or create_application(["quire-tests"])
    from quire.presentation import i18n
    i18n.install("en", app)  # tests always run in English
    return app


@pytest.fixture
def splash(app):
    s = SplashScreen("1.2.3")
    s.STEP_MS = 5
    s.FADE_IN_MS = 5
    s.FADE_OUT_MS = 5
    s.MIN_VISIBLE_MS = 40
    yield s
    try:
        s.close_now()
    except RuntimeError:
        pass  # it already deleted itself


def visible(splash):
    try:
        return splash.isVisible()
    except RuntimeError:
        return False  # gone for good: it deletes itself when it fades out


def wait(ms):
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        QCoreApplication.processEvents()


def test_it_paints_the_name_and_the_version(splash):
    splash.show()
    splash.step("Opening your data…", 0.5)
    image = splash.grab().toImage()
    assert not image.isNull() and image.width() > 600 and image.height() > 300
    assert splash.status == "Opening your data…"
    assert splash.version == "1.2.3"
    # The card is dark, the progress bar amber: both really got drawn.
    centre = image.pixelColor(image.width() // 2, image.height() // 2)
    assert centre.lightness() < 120
    bar = image.pixelColor(60, image.height() - 28 - 3)
    assert bar.red() > 200 and bar.blue() < 80


def test_the_bar_only_moves_forward_and_reaches_where_it_was_told(splash):
    splash.show()
    splash.step("One", 0.3)
    assert splash.progress == pytest.approx(0.3, abs=0.01)
    splash.step("Two", 0.1)  # never backwards
    assert splash.progress == pytest.approx(0.3, abs=0.01)
    splash.step("Three", 1.0)
    assert splash.progress == pytest.approx(1.0, abs=0.01)
    splash.step("Four", 5.0)  # clamped
    assert splash.progress <= 1.0


def test_it_stays_up_a_minimum_time_then_goes_away_by_itself(splash):
    splash.MIN_VISIBLE_MS = 120
    splash.show()
    splash.finish()
    wait(40)
    assert visible(splash)  # started too fast to read: it waits
    wait(400)
    assert not visible(splash)


def test_finishing_twice_and_stepping_afterwards_are_harmless(splash):
    splash.show()
    splash.finish()
    splash.finish()
    splash.step("late", 0.9)  # ignored once it is leaving
    assert splash.status != "late"
    wait(200)
    assert not visible(splash)


def test_close_now_is_immediate(splash):
    splash.show()
    splash.close_now()
    assert not visible(splash)
