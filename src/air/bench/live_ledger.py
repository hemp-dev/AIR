"""Model-call accounting for provider-backed benchmark experiments."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .live_models import (
    LiveCallRecord,
    PricingBreakdown,
    PricingProfile,
    calculate_pricing,
)


@dataclass(frozen=True, slots=True)
class LiveLedgerTotals:
    """Cumulative exact usage and timing totals for a call collection."""

    model_calls: int
    request_bytes: int
    communication_bytes: int
    materialized_context_bytes: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    preprocessing_seconds: float | None
    provider_seconds: float | None
    total_seconds: float | None
    retries: int

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    def to_json_obj(self) -> dict[str, object]:
        return {
            "cached_input_tokens": self.cached_input_tokens,
            "communication_bytes": self.communication_bytes,
            "input_tokens": self.input_tokens,
            "materialized_context_bytes": self.materialized_context_bytes,
            "model_calls": self.model_calls,
            "output_tokens": self.output_tokens,
            "preprocessing_seconds": self.preprocessing_seconds,
            "provider_seconds": self.provider_seconds,
            "reasoning_tokens": self.reasoning_tokens,
            "request_bytes": self.request_bytes,
            "retries": self.retries,
            "total_model_seconds": self.total_seconds,
            "total_tokens": self.total_tokens,
        }


class ModelCallLedger:
    """Append-only ledger with nullable-safe cumulative aggregation."""

    def __init__(self) -> None:
        self._records: list[LiveCallRecord] = []

    def append(self, record: LiveCallRecord) -> None:
        expected_index = len(self._records) + 1
        if record.call_index != expected_index:
            raise ValueError(
                f"call index must be contiguous: expected {expected_index}, got {record.call_index}"
            )
        self._records.append(record)

    @property
    def records(self) -> tuple[LiveCallRecord, ...]:
        return tuple(self._records)

    def totals(self) -> LiveLedgerTotals:
        return LiveLedgerTotals(
            model_calls=len(self._records),
            request_bytes=sum(record.request_bytes for record in self._records),
            communication_bytes=sum(record.communication_bytes for record in self._records),
            materialized_context_bytes=sum(
                record.materialized_context_bytes for record in self._records
            ),
            input_tokens=_sum_int(record.input_tokens for record in self._records),
            cached_input_tokens=_sum_int(record.cached_input_tokens for record in self._records),
            output_tokens=_sum_int(record.output_tokens for record in self._records),
            reasoning_tokens=_sum_int(record.reasoning_tokens for record in self._records),
            preprocessing_seconds=_sum_float(
                record.preprocessing_seconds for record in self._records
            ),
            provider_seconds=_sum_float(record.provider_seconds for record in self._records),
            total_seconds=_sum_float(record.total_seconds for record in self._records),
            retries=sum(record.retry_count for record in self._records),
        )

    def pricing(self, profile: PricingProfile | None) -> PricingBreakdown | None:
        if profile is None:
            return None
        totals = self.totals()
        return calculate_pricing(
            totals.input_tokens,
            totals.cached_input_tokens,
            totals.output_tokens,
            profile,
        )


def _sum_int(values: Iterable[int | None]) -> int | None:
    materialized = list(values)
    if not materialized or any(value is None for value in materialized):
        return None
    return sum(value for value in materialized if value is not None)


def _sum_float(values: Iterable[float | None]) -> float | None:
    materialized = list(values)
    if not materialized or any(value is None for value in materialized):
        return None
    return sum(value for value in materialized if value is not None)
