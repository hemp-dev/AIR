"""Representation-independent communication and context ledgers."""

from __future__ import annotations

from dataclasses import dataclass

from .models import TokenCounter, canonical_bytes


@dataclass(frozen=True, slots=True)
class CommunicationRecord:
    """One logical transport event, excluding any separately materialized context."""

    sequence: int
    sender: str
    receiver: str
    kind: str
    payload_size_bytes: int
    logical_content_id: str
    token_count: int | None = None

    def to_json_obj(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "logical_content_id": self.logical_content_id,
            "payload_size_bytes": self.payload_size_bytes,
            "receiver": self.receiver,
            "sender": self.sender,
            "sequence": self.sequence,
            "token_count": self.token_count,
        }


@dataclass(frozen=True, slots=True)
class ContextMaterialization:
    """One payload that would enter a consumer's model/inference context."""

    sequence: int
    consumer: str
    source_ref: str
    bytes: int
    reason: str
    token_count: int | None = None

    def to_json_obj(self) -> dict[str, object]:
        return {
            "bytes": self.bytes,
            "consumer": self.consumer,
            "reason": self.reason,
            "sequence": self.sequence,
            "source_ref": self.source_ref,
            "token_count": self.token_count,
        }


class CommunicationLedger:
    """Append-only accounting shared by every benchmark mode."""

    def __init__(self, token_counter: TokenCounter) -> None:
        self.token_counter = token_counter
        self._communications: list[CommunicationRecord] = []
        self._materializations: list[ContextMaterialization] = []
        self._source_context_bytes = 0
        self._artifact_bytes = 0

    def record_source_context(self, payload: object) -> int:
        """Record one authoritative fixture context, generated once."""

        size = len(canonical_bytes(payload))
        self._source_context_bytes += size
        return size

    def record_artifact(self, payload: object) -> int:
        size = len(canonical_bytes(payload))
        self._artifact_bytes += size
        return size

    def send(
        self,
        sender: str,
        receiver: str,
        kind: str,
        payload: object,
        *,
        logical_content_id: str,
        model: str | None = None,
    ) -> CommunicationRecord:
        """Record transport bytes without implicitly materializing a ref."""

        encoded = canonical_bytes(payload)
        text = encoded.decode("utf-8")
        record = CommunicationRecord(
            sequence=len(self._communications) + 1,
            sender=sender,
            receiver=receiver,
            kind=kind,
            payload_size_bytes=len(encoded),
            logical_content_id=logical_content_id,
            token_count=self.token_counter.count(text, model),
        )
        self._communications.append(record)
        return record

    def materialize(
        self,
        consumer: str,
        source_ref: str,
        payload: object,
        *,
        reason: str,
        model: str | None = None,
    ) -> ContextMaterialization:
        """Record inference-context bytes separately from transport bytes."""

        encoded = canonical_bytes(payload)
        text = encoded.decode("utf-8")
        materialization = ContextMaterialization(
            sequence=len(self._materializations) + 1,
            consumer=consumer,
            source_ref=source_ref,
            bytes=len(encoded),
            reason=reason,
            token_count=self.token_counter.count(text, model),
        )
        self._materializations.append(materialization)
        return materialization

    @property
    def communications(self) -> tuple[CommunicationRecord, ...]:
        return tuple(self._communications)

    @property
    def materializations(self) -> tuple[ContextMaterialization, ...]:
        return tuple(self._materializations)

    @property
    def source_context_bytes(self) -> int:
        return self._source_context_bytes

    @property
    def artifact_bytes(self) -> int:
        return self._artifact_bytes

    @property
    def serialized_message_bytes(self) -> int:
        return sum(item.payload_size_bytes for item in self._communications)

    @property
    def materialized_context_bytes(self) -> int:
        return sum(item.bytes for item in self._materializations)

    @property
    def input_tokens(self) -> int | None:
        values = [item.token_count for item in self._materializations]
        return _sum_or_none(values)

    @property
    def output_tokens(self) -> int | None:
        values = [item.token_count for item in self._communications]
        return _sum_or_none(values)

    def to_json_obj(self) -> dict[str, object]:
        return {
            "communications": [item.to_json_obj() for item in self._communications],
            "context_materializations": [item.to_json_obj() for item in self._materializations],
            "source_context_bytes": self.source_context_bytes,
            "artifact_bytes": self.artifact_bytes,
            "serialized_message_bytes": self.serialized_message_bytes,
            "materialized_context_bytes": self.materialized_context_bytes,
        }


def _sum_or_none(values: list[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


class MetricsCollector(CommunicationLedger):
    """Public compatibility name for the benchmark's ledger collector."""
