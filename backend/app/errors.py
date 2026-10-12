"""Errors that are safe to show to a caller."""


class APIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OpenMeteoError(Exception):
    """The public weather archive failed or returned an unusable payload."""
