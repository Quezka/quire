"""Errors callers of the application may see, phrased for the user.

Domain rule violations are re-exported here so outer layers never import the
domain to catch them.
"""
from ..domain.errors import DomainError, NotFound, ValidationError

__all__ = ["ApplicationError", "AuthenticationError", "CredentialStorageError", "DomainError",
           "NotConnected", "NotFound", "RegisterError", "ValidationError"]



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
