"""Typed failures for the in-memory AIR StateStore."""

from __future__ import annotations


class StateError(ValueError):
    """Base class for state and patch failures."""


class StateNotFoundError(StateError):
    """Raised when a named or immutable state object does not exist."""


class InvalidPatchError(StateError):
    """Raised when a patch is malformed before commit."""


class StaleVersionError(StateError):
    """Raised when a patch was based on an old current state version."""

    def __init__(self, target: str, expected: int, actual: int) -> None:
        self.target = target
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"stale state version for {target}: expected v{expected}, current is v{actual}"
        )


class WriteScopeError(StateError):
    """Raised when changed paths escape a patch's declared write set."""


class PatchIntegrityError(StateError):
    """Raised when a patch ID is replayed with different content."""
