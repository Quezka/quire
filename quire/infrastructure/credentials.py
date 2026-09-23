"""Keeps the school register password in the operating system's keyring
(GNOME Keyring / KWallet on Linux, Credential Manager on Windows)."""
from __future__ import annotations

import json

from .. import APP_ID
from ..application.errors import CredentialStorageError
from ..application.ports import Credentials


class KeyringCredentialStore:
    def __init__(self, account: str = "classeviva"):
        self._account = account

    def load(self) -> Credentials | None:
        try:
            import keyring

            raw = keyring.get_password(APP_ID, self._account)
        except Exception:  # no keyring backend, locked keyring, ...
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return Credentials(data["username"], data["password"])
        except (ValueError, KeyError, TypeError):
            return None

    def save(self, credentials: Credentials) -> None:
        try:
            import keyring

            keyring.set_password(APP_ID, self._account, json.dumps(
                {"username": credentials.username, "password": credentials.password}))
        except Exception as e:
            raise CredentialStorageError(
                "Couldn't save the password in your system keyring. On Linux, make sure "
                "GNOME Keyring or KWallet is running.") from e

    def clear(self) -> None:
        try:
            import keyring

            keyring.delete_password(APP_ID, self._account)
        except Exception:
            pass


class MemoryCredentialStore:
    """Keeps credentials only for the lifetime of the process (tests, demo)."""

    def __init__(self, credentials: Credentials | None = None):
        self._credentials = credentials

    def load(self):
        return self._credentials

    def save(self, credentials):
        self._credentials = credentials

    def clear(self):
        self._credentials = None
