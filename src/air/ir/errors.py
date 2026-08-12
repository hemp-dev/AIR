"""Errors raised while constructing or decoding canonical AIR objects."""

from __future__ import annotations


class AIRModelError(ValueError):
    """Base class for invalid canonical AIR data."""


class InvalidIdentifierError(AIRModelError):
    """Raised when an AIR identifier or reference is malformed."""


class DuplicateIdError(AIRModelError):
    """Raised when a program defines an operation or SSA result twice."""


class SerializationError(AIRModelError):
    """Raised when canonical AIR-JSON is malformed or unsupported."""
