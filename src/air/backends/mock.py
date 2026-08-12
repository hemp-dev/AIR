"""Deterministic in-process agent and tool executors for AIR tests."""

from __future__ import annotations

from collections.abc import Callable

from ..runtime.errors import BackendFailure
from .base import BackendRequest

Handler = Callable[[object], object]


class MockAgentExecutor:
    """Explicit actor-to-handler registry; no network or provider dependency."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self.calls: list[BackendRequest] = []

    def register(self, actor: str, handler: Handler) -> None:
        self._handlers[actor] = handler

    def invoke(self, request: BackendRequest) -> object:
        self.calls.append(request)
        try:
            handler = self._handlers[request.target]
        except KeyError as exc:
            raise BackendFailure(f"no mock agent registered for {request.target}") from exc
        try:
            return handler(request.input)
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(f"mock agent {request.target} failed: {exc}") from exc


class MockToolExecutor:
    """Explicit tool-to-handler registry; calls are observable for tests."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self.calls: list[BackendRequest] = []

    def register(self, tool: str, handler: Handler) -> None:
        self._handlers[tool] = handler

    def call(self, request: BackendRequest) -> object:
        self.calls.append(request)
        try:
            handler = self._handlers[request.target]
        except KeyError as exc:
            raise BackendFailure(f"no mock tool registered for {request.target}") from exc
        try:
            return handler(request.input)
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(f"mock tool {request.target} failed: {exc}") from exc
