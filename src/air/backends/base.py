"""Provider-independent local backend protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BackendRequest:
    """Verified invocation request passed to a mock/provider adapter."""

    target: str
    input: object
    op_id: str


class AgentExecutor(Protocol):
    """Synchronous typed agent invocation boundary."""

    def invoke(self, request: BackendRequest) -> object:
        """Return a deterministic typed value or raise a controlled failure."""


class ToolExecutor(Protocol):
    """Synchronous typed tool invocation boundary."""

    def call(self, request: BackendRequest) -> object:
        """Return a deterministic typed value or raise a controlled failure."""
