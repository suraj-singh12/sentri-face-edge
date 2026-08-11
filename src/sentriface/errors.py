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


class GraphProjectionRebuildRefused(SentriFaceError):
    """Raised when authoritative integrity findings make rebuild unsafe."""

    def __init__(self, operation_id: str, report: object, message: str) -> None:
        super().__init__(message)
        self.operation_id = operation_id
        self.report = report


class GraphProjectionPostcheckError(SentriFaceError):
    """Raised when a committed rebuild fails its post-commit read-only check."""

    def __init__(self, result: dict, report: object) -> None:
        super().__init__(
            "Graph projection rebuild committed, but the post-commit integrity check failed"
        )
        self.result = result
        self.report = report


class StructuredRepairRefused(SentriFaceError):
    """Raised when a finding-bound structured repair is stale or unsafe."""

    def __init__(self, message: str, *, report: object | None = None) -> None:
        super().__init__(message)
        self.report = report


class StructuredRepairPostcheckError(SentriFaceError):
    """Raised when a committed structured repair fails its read-only post-check."""

    def __init__(self, result: dict, report: object) -> None:
        super().__init__(
            "Structured repair committed, but the post-commit integrity check failed"
        )
        self.result = result
        self.report = report
