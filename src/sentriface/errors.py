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


class QueueCancellationError(SentriFaceError):
    """Raised when an active queue scan reaches a cancellation checkpoint."""

    def __init__(self, session_id: str, phase: str) -> None:
        super().__init__("Queue processing was cancelled")
        self.session_id = session_id
        self.phase = phase
