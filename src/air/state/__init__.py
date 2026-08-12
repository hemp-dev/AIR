"""Immutable shared semantic state for AIR runtime execution."""

from ..ir.refs import StateRef, normalize_relative_path, normalize_write_scope
from .errors import (
    InvalidPatchError,
    PatchIntegrityError,
    StaleVersionError,
    StateError,
    StateNotFoundError,
    WriteScopeError,
)
from .objects import StateObject, StateProjection
from .patch import Patch
from .store import CommitRecord, StateStore

__all__ = [
    "CommitRecord",
    "InvalidPatchError",
    "Patch",
    "PatchIntegrityError",
    "StateError",
    "StateNotFoundError",
    "StateRef",
    "StateObject",
    "StateProjection",
    "StateStore",
    "StaleVersionError",
    "WriteScopeError",
    "normalize_relative_path",
    "normalize_write_scope",
]
