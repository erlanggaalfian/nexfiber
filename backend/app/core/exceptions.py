class AppError(Exception):
    """Base for all domain errors; mapped to HTTP status in main.py exception handler."""

    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ForbiddenError(AppError):
    status_code = 403


class ValidationAppError(AppError):
    status_code = 422


class DriverError(AppError):
    """OLT returned an error or operation could not be verified from output (PRD 4.3)."""

    status_code = 502

class CommandRejectedError(DriverError):
    """OLT answered with an error pattern — deterministic, so the worker does not retry it."""
