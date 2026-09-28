"""Errors callers of the application may see, phrased for the user.

Domain rule violations are re-exported here so outer layers never import the
domain to catch them.
"""
from ..domain.errors import DomainError, NotFound, ValidationError

__all__ = ["ApplicationError", "AuthenticationError", "CloudAuthError", "CredentialStorageError",
           "DomainError", "NotConnected", "NotFound", "RegisterError", "SyncError",
           "StartupError", "SyncNotSetUp", "UpdateError", "ValidationError"]



class ApplicationError(Exception):
    """Base class for errors the UI shows as a message."""


class RegisterError(ApplicationError):
    """The school register could not be reached or answered unexpectedly."""


class AuthenticationError(RegisterError):
    """The register rejected the username or password."""


class NotConnected(ApplicationError):
    """No school register account has been set up."""


class CredentialStorageError(ApplicationError):
    """The password could not be stored safely."""


class SyncError(ApplicationError):
    """The sync server couldn't be reached or refused the request."""


class CloudAuthError(SyncError):
    """The cloud account rejected the email, password or saved sign-in."""


class SyncNotSetUp(ApplicationError):
    """Sync hasn't been set up on this device."""


class UpdateError(ApplicationError):
    """Checking for, downloading or installing an update didn't work."""


class StartupError(ApplicationError):
    """Starting Quire with the system couldn't be switched on or off."""
