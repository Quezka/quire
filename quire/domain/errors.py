class DomainError(Exception):
    """Base class for rule violations the user can act on."""


class ValidationError(DomainError):
    """An entity was given values that break a business rule."""


class NotFound(DomainError):
    """A referenced entity does not exist."""
