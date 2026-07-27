from __future__ import annotations


class SentriFaceError(Exception):
    """User-facing application error."""


class InputImageError(SentriFaceError):
    """The input image could not be read or processed."""


class InputValidationError(SentriFaceError):
    """A user-supplied value is unsafe, malformed, or unsupported."""

    def __init__(self, message: str, reason: str = "invalid_input") -> None:
        super().__init__(message)
        self.reason = reason


class ModelSetupError(SentriFaceError):
    """The configured model/runtime is missing or invalid."""
