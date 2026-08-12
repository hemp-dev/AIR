"""Trust labels and immutable provenance metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .ids import ActorRef, OpId, ValueRef


class TrustLabel(StrEnum):
    """Semantic trust labels; their declaration order has no ranking meaning."""

    VERIFIED = "Verified"
    SYSTEM_DERIVED = "SystemDerived"
    AGENT_DERIVED = "AgentDerived"
    USER_SUPPLIED = "UserSupplied"
    EXTERNAL_UNTRUSTED = "ExternalUntrusted"
    UNKNOWN = "Unknown"

    @classmethod
    def from_json(cls, value: object) -> TrustLabel:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"trust label must be a string, got {type(value).__name__}")
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown trust label: {value!r}") from exc


def trust_transition_allowed(
    source: TrustLabel,
    target: TrustLabel,
    *,
    explicit_verification: bool = False,
) -> bool:
    """Return whether a semantic value may receive ``target`` trust.

    AIR deliberately has no implicit total ordering for trust.  A transition to
    ``Verified`` is allowed only when an explicit verifier/attestation operation
    is present; retaining a label is always allowed.
    """

    if source == target:
        return True
    if target == TrustLabel.VERIFIED:
        return explicit_verification
    return False


@dataclass(frozen=True, slots=True)
class Provenance:
    """Source and production metadata carried by semantic values."""

    source_refs: tuple[str | ValueRef, ...] = field(default_factory=tuple)
    produced_by: ActorRef | None = None
    operation_id: OpId | None = None
    timestamp: datetime | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized_sources: list[str | ValueRef] = []
        for source in self.source_refs:
            if isinstance(source, ValueRef):
                normalized_sources.append(source)
            elif isinstance(source, str) and source:
                normalized_sources.append(source)
            else:
                raise ValueError(f"invalid provenance source reference: {source!r}")
        normalized_evidence: list[str] = []
        for evidence in self.evidence_refs:
            if not isinstance(evidence, str) or not evidence:
                raise ValueError(f"invalid provenance evidence reference: {evidence!r}")
            normalized_evidence.append(evidence)

        if self.produced_by is not None and not isinstance(self.produced_by, ActorRef):
            object.__setattr__(self, "produced_by", ActorRef(self.produced_by))
        if self.operation_id is not None and not isinstance(self.operation_id, OpId):
            object.__setattr__(self, "operation_id", OpId(self.operation_id))
        object.__setattr__(self, "source_refs", tuple(normalized_sources))
        object.__setattr__(self, "evidence_refs", tuple(normalized_evidence))

    @classmethod
    def from_json_obj(cls, raw: object) -> Provenance:
        if not isinstance(raw, dict):
            raise ValueError("provenance must be an object")
        allowed = {"source_refs", "produced_by", "operation_id", "timestamp", "evidence_refs"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown provenance fields: {sorted(unknown)!r}")
        source_refs_raw = raw.get("source_refs", [])
        evidence_refs_raw = raw.get("evidence_refs", [])
        if not isinstance(source_refs_raw, list) or not isinstance(evidence_refs_raw, list):
            raise ValueError("provenance reference fields must be arrays")
        sources: list[str | ValueRef] = []
        for source in source_refs_raw:
            if isinstance(source, dict) and source.get("kind") == "ref":
                sources.append(ValueRef(source["id"]))
            elif isinstance(source, str):
                sources.append(source)
            else:
                raise ValueError(f"invalid provenance source: {source!r}")
        timestamp_raw = raw.get("timestamp")
        timestamp = None
        if timestamp_raw is not None:
            if not isinstance(timestamp_raw, str):
                raise ValueError("provenance timestamp must be an ISO string")
            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
            except ValueError as exc:
                raise ValueError(f"invalid provenance timestamp: {timestamp_raw!r}") from exc
        return cls(
            source_refs=tuple(sources),
            produced_by=ActorRef(raw["produced_by"])
            if raw.get("produced_by") is not None
            else None,
            operation_id=OpId(raw["operation_id"]) if raw.get("operation_id") is not None else None,
            timestamp=timestamp,
            evidence_refs=tuple(evidence_refs_raw),
        )

    def to_json_obj(self) -> dict[str, object]:
        sources: list[object] = []
        for source in self.source_refs:
            if isinstance(source, ValueRef):
                sources.append({"kind": "ref", "id": str(source.result_id)})
            else:
                sources.append(source)
        return {
            "source_refs": sources,
            "produced_by": str(self.produced_by) if self.produced_by is not None else None,
            "operation_id": str(self.operation_id) if self.operation_id is not None else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp is not None else None,
            "evidence_refs": list(self.evidence_refs),
        }
