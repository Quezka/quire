"""Failures of outside systems, phrased for the user."""


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
