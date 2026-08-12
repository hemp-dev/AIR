"""Agent IR v0.1 package."""

from . import ir as _ir
from .backends import (
    AgentExecutor,
    BackendRequest,
    MockAgentExecutor,
    MockToolExecutor,
    ToolExecutor,
)
from .ir import *  # noqa: F403
from .projection import OperatorMessage, OperatorProjection
from .runtime import Event, EventLog, ExecutionResult, FutureValue, Runtime
from .state import (
    CommitRecord,
    InvalidPatchError,
    Patch,
    PatchIntegrityError,
    StaleVersionError,
    StateError,
    StateNotFoundError,
    StateObject,
    StateProjection,
    StateStore,
    WriteScopeError,
)
from .verifier import (
    Diagnostic,
    Severity,
    VerificationContext,
    VerificationError,
    VerificationReport,
    VerifiedProgram,
    Verifier,
)

__all__ = [
    *_ir.__all__,
    "AgentExecutor",
    "BackendRequest",
    "Diagnostic",
    "CommitRecord",
    "Event",
    "EventLog",
    "ExecutionResult",
    "FutureValue",
    "MockAgentExecutor",
    "MockToolExecutor",
    "OperatorMessage",
    "OperatorProjection",
    "Patch",
    "PatchIntegrityError",
    "Runtime",
    "Severity",
    "StateError",
    "StateNotFoundError",
    "StateObject",
    "StateProjection",
    "StateStore",
    "StaleVersionError",
    "ToolExecutor",
    "VerifiedProgram",
    "VerificationContext",
    "VerificationError",
    "VerificationReport",
    "Verifier",
    "InvalidPatchError",
    "WriteScopeError",
]
