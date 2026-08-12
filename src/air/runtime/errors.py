"""Typed runtime failures surfaced by AIR execution."""

from __future__ import annotations


class RuntimeErrorBase(RuntimeError):
    """Base class for controlled runtime failures."""


class BackendFailure(RuntimeErrorBase):
    """Raised when a mock agent/tool backend fails."""


class AssertionFailure(RuntimeErrorBase):
    """Raised by a failed deterministic verify.assert operation."""


class HumanRequired(RuntimeErrorBase):
    """Raised when execution reaches a human authorization boundary."""


class StateFailure(RuntimeErrorBase):
    """Controlled wrapper for a StateStore failure and its original typed cause."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


class UnknownRuntimeOperation(RuntimeErrorBase):
    """Defensive failure if an unverified/unknown opcode reaches dispatch."""
