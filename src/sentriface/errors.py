from __future__ import annotations


class SentriFaceError(Exception):
    """User-facing application error."""


class InputImageError(SentriFaceError):
    """The input image could not be read or processed."""


class ModelSetupError(SentriFaceError):
    """The configured model/runtime is missing or invalid."""

