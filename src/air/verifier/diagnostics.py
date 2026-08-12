"""Structured diagnostics emitted by the deterministic AIR verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..ir.operations import SourceLocation


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One stable verifier diagnostic."""

    code: str
    severity: Severity
    message: str
    op_id: str | None = None
    source: SourceLocation | None = None
    related_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Complete result of static verification."""

    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == Severity.ERROR for diagnostic in self.diagnostics)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(
            diagnostic for diagnostic in self.diagnostics if diagnostic.severity == Severity.ERROR
        )


class VerificationError(ValueError):
    """Raised when a caller explicitly requires a valid program."""

    def __init__(self, report: VerificationReport) -> None:
        self.report = report
        summary = "; ".join(f"{item.code}: {item.message}" for item in report.errors)
        super().__init__(summary or "AIR program verification failed")
