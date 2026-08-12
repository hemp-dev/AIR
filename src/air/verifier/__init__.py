"""Static, deterministic AIR verification."""

from .diagnostics import Diagnostic, Severity, VerificationError, VerificationReport
from .registry import CORE_OPCODE_SPECS, OpcodeRegistry, OpcodeSpec
from .verifier import VerificationContext, VerifiedProgram, Verifier

__all__ = [
    "CORE_OPCODE_SPECS",
    "Diagnostic",
    "OpcodeRegistry",
    "OpcodeSpec",
    "Severity",
    "VerifiedProgram",
    "VerificationContext",
    "VerificationError",
    "VerificationReport",
    "Verifier",
]
