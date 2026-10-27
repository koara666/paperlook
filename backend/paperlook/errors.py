"""User-facing error type. The message is shown in the UI verbatim, so write it in plain Chinese
and include what the user can do about it."""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
