"""Picks the cloud backend a device is set up with (a Quire server or a Firebase project)."""
from __future__ import annotations

from ..application.ports import SERVER, CloudBackend, CloudConfig
from .firebase import FirebaseCloud
from .quire_server import QuireServerCloud


class RoutingCloud:
    """Sends each call to the adapter for `config.backend`, so a device can move from Firebase
    to a Quire server without the sync service knowing which is which."""

    def __init__(self, firebase: CloudBackend | None = None, server: CloudBackend | None = None):
        self._firebase = firebase or FirebaseCloud()
        self._server = server or QuireServerCloud()

    def _for(self, config: CloudConfig) -> CloudBackend:
        return self._server if config.backend == SERVER else self._firebase

    def sign_up(self, config, email, password, invite=""):
        return self._for(config).sign_up(config, email, password, invite)

    def sign_in(self, config, email, password):
        return self._for(config).sign_in(config, email, password)

    def refresh(self, config, refresh_token):
        return self._for(config).refresh(config, refresh_token)

    def pull(self, config, session, cursor):
        return self._for(config).pull(config, session, cursor)

    def push(self, config, session, records):
        return self._for(config).push(config, session, records)
