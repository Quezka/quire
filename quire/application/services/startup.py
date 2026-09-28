from __future__ import annotations

from ..errors import StartupError
from ..ports import KeyValueStore, LoginItem


class StartupService:
    """Use cases for how Quire runs: in the background when its window is closed (so
    reminders and syncing carry on), and starting when you log in."""

    PREFIX = "startup."

    def __init__(self, login_item: LoginItem, settings: KeyValueStore):
        self._login_item = login_item
        self._settings = settings

    def background_on_close(self) -> bool:
        return self._settings.get(self.PREFIX + "background") != "0"

    def set_background_on_close(self, on: bool) -> None:
        self._settings.set(self.PREFIX + "background", "1" if on else "0")

    def can_start_on_login(self) -> bool:
        return self._login_item.supported()

    def start_on_login(self) -> bool:
        return self._login_item.supported() and self._login_item.enabled()

    def set_start_on_login(self, on: bool) -> None:
        try:
            self._login_item.set_enabled(on)
        except OSError as e:
            raise StartupError("Couldn't change whether Quire starts when you log in.") from e

    def refresh_login_item(self) -> None:
        """Rewrite the login entry if it's on, so it follows Quire if it moved or updated."""
        if self.start_on_login():
            try:
                self._login_item.set_enabled(True)
            except OSError:
                pass  # a convenience: never stop Quire from starting over it
