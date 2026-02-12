"""Custom exception hierarchy for backend layers."""


class CareerScoutError(Exception):
    """Base application exception."""


class RepositoryError(CareerScoutError):
    """Raised when repository data access fails."""


class DuplicateError(RepositoryError):
    """Raised when a duplicate record violates a unique constraint."""


class DuplicateJobError(DuplicateError):
    """Raised when a job already exists for external_id + platform."""


class NotFoundError(CareerScoutError):
    """Raised when a requested resource does not exist."""


class BusinessLogicError(CareerScoutError):
    """Raised when a service layer business rule fails."""


__all__ = [
    "BusinessLogicError",
    "CareerScoutError",
    "DuplicateError",
    "DuplicateJobError",
    "NotFoundError",
    "RepositoryError",
]
