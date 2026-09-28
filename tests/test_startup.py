"""Running in the background and starting at login."""
import pytest

from quire.application.errors import StartupError
from quire.infrastructure.login_item import (
    NoLoginItem, XdgAutostart, desktop_exec, launch_command,
)

from .fakes import FakeLoginItem


def test_background_is_on_by_default_and_can_be_switched_off(services):
    assert services.startup.background_on_close()
    services.startup.set_background_on_close(False)
    assert not services.startup.background_on_close()


def test_start_on_login(services, login_item):
    assert not services.startup.start_on_login()
    services.startup.set_start_on_login(True)
    assert services.startup.start_on_login() and login_item.on
    services.startup.refresh_login_item()  # rewritten each launch, to follow the app
    assert login_item.writes == 2
    services.startup.set_start_on_login(False)
    assert not login_item.on


def test_unsupported_systems_say_so(services):
    services.startup._login_item = FakeLoginItem(supported=False)
    assert not services.startup.can_start_on_login()
    with pytest.raises(StartupError):
        services.startup.set_start_on_login(True)
    services.startup.refresh_login_item()  # never raises


def test_launch_command_starts_in_the_background():
    assert launch_command(True, "/opt/quire/Quire") == ["/opt/quire/Quire", "--background"]
    command = launch_command(False, "/usr/bin/python3")
    assert command[1:] == ["-m", "quire", "--background"]


def test_xdg_autostart_entry(tmp_path):
    item = XdgAutostart(tmp_path, ["/opt/my apps/Quire", "--background"])
    assert not item.enabled()
    item.set_enabled(True)
    text = item.path.read_text()
    assert item.path == tmp_path / "autostart" / "io.github.quezka.Quire.desktop"
    assert 'Exec="/opt/my apps/Quire" --background' in text
    item.set_enabled(False)
    assert not item.enabled()
    assert desktop_exec(["a$b"]) == '"a\\$b"'
    assert not NoLoginItem().supported()
