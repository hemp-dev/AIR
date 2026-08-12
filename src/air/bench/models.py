"""Canonical data models for the deterministic AIR benchmark harness."""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Protocol, cast

from ..ir import AIR_VERSION, JsonInput

BENCHMARK_VERSION = "0.1"


class BenchmarkEquivalenceError(ValueError):
    """Raised when deterministic mode outputs are not semantically equivalent."""


class BenchmarkMode(StrEnum):
    """Representation/execution modes compared by the benchmark."""

    NL = "NL"
    JSON = "JSON"
    SJSON = "SJSON"
    AIR = "AIR"

    @classmethod
    def parse_many(cls, raw: str) -> tuple[BenchmarkMode, ...]:
        """Parse a comma-separated mode list while preserving user order."""

        values: list[BenchmarkMode] = []
        for item in raw.split(","):
            name = item.strip().upper()
            if not name:
                continue
            try:
                mode = cls(name)
            except ValueError as exc:
                raise ValueError(f"unknown benchmark mode: {item!r}") from exc
            if mode not in values:
                values.append(mode)
        if not values:
            raise ValueError("at least one benchmark mode is required")
        return tuple(values)


class TokenCounter(Protocol):
    """Optional exact-token measurement boundary.

    Implementations must return ``None`` when they cannot provide an exact
    count. The benchmark never derives token counts from characters or bytes.
    """

    @property
    def profile(self) -> str:
        """Return a stable, non-secret tokenizer profile name."""

    @property
    def exact(self) -> bool:
        """Whether returned counts are exact for the declared profile."""

    def count(self, text: str, model: str | None = None) -> int | None:
        """Count tokens for one serialized payload, if supported."""


class NoopTokenCounter:
    """Default counter used by the offline deterministic benchmark."""

    profile = "none"
    exact = False

    def count(self, text: str, model: str | None = None) -> None:
        del text, model
        return None


@dataclass(frozen=True, slots=True)
class FunctionTokenCounter:
    """Adapter for an externally supplied tokenizer function.

    The harness does not ship a tokenizer dependency. Callers may inject one
    and explicitly label whether its result is exact for a model profile.
    """

    counter: Any
    profile: str
    exact: bool = True

    def count(self, text: str, model: str | None = None) -> int | None:
        value = self.counter(text, model)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("token counter must return a non-negative integer or None")
        return value


def canonical_bytes(value: object) -> bytes:
    """Serialize a benchmark payload deterministically for byte accounting."""

    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(
        json_compatible(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def json_compatible(value: object) -> JsonInput:
    """Convert AIR/runtime values into ordinary JSON-compatible containers."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    json_value = getattr(value, "json_value", None)
    if callable(json_value):
        return json_compatible(json_value())
    raw_value = getattr(value, "value", None)
    if raw_value is not None and raw_value is not value:
        return json_compatible(raw_value)
    return str(value)


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    """Raw per-run metrics; unavailable measurements remain ``None``."""

    task_success: bool | None = None
    expected_result_match: bool | None = None
    source_context_bytes: int | None = None
    materialized_context_bytes: int | None = None
    serialized_message_bytes: int | None = None
    coordination_bytes: int | None = None
    artifact_bytes: int | None = None
    message_count: int | None = None
    state_read_count: int | None = None
    state_projection_count: int | None = None
    state_patch_count: int | None = None
    state_commit_count: int | None = None
    state_conflict_count: int | None = None
    operation_count: int | None = None
    agent_invocation_count: int | None = None
    tool_invocation_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    llm_call_count: int | None = None
    preprocessing_time_ms: float | None = None
    execution_time_ms: float | None = None
    end_to_end_time_ms: float | None = None
    backend_latency_ms: float | None = None
    verification_latency_ms: float | None = None
    state_latency_ms: float | None = None
    unauthorized_attempts: int | None = None
    unauthorized_executions: int | None = None
    trust_violations: int | None = None
    verification_failures: int | None = None
    event_count: int | None = None
    provenance_coverage: float | None = None
    retries: int | None = None

    def with_timing(self, *, execution_ms: float, end_to_end_ms: float) -> BenchmarkMetrics:
        """Return a copy with runner timing fields populated."""

        return replace(
            self,
            execution_time_ms=execution_ms,
            end_to_end_time_ms=end_to_end_ms,
        )

    def to_json_obj(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ScenarioExecution:
    """Mode-specific execution output for one logical scenario case."""

    expected_result: JsonInput
    actual_result: JsonInput
    metrics: BenchmarkMetrics
    details: Mapping[str, JsonInput] = field(default_factory=dict)
    failure_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.actual_result == self.expected_result

    @property
    def semantic_score(self) -> float:
        return 1.0 if self.success else 0.0


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Machine-readable raw result for one scenario/mode/repetition."""

    benchmark_version: str
    suite: str
    scenario: str
    mode: BenchmarkMode
    run_id: str
    success: bool
    semantic_score: float
    expected_result: JsonInput
    actual_result: JsonInput
    metrics: BenchmarkMetrics
    config: Mapping[str, JsonInput]
    environment: Mapping[str, JsonInput]
    details: Mapping[str, JsonInput] = field(default_factory=dict)
    failure_reason: str | None = None

    def to_json_obj(self) -> dict[str, object]:
        result: dict[str, object] = {
            "actual_result": self.actual_result,
            "benchmark_version": self.benchmark_version,
            "config": dict(self.config),
            "details": dict(self.details),
            "environment": dict(self.environment),
            "expected_result": self.expected_result,
            "metrics": self.metrics.to_json_obj(),
            "mode": self.mode.value,
            "run_id": self.run_id,
            "scenario": self.scenario,
            "semantic_score": self.semantic_score,
            "success": self.success,
        }
        if self.failure_reason is not None:
            result["failure_reason"] = self.failure_reason
        return result


def benchmark_environment(token_counter: TokenCounter) -> dict[str, JsonInput]:
    """Return reproducibility metadata without machine-specific paths."""

    return {
        "air_version": AIR_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "tokenizer_profile": token_counter.profile,
        "tokenizer_exact": token_counter.exact,
    }


def safe_json(value: object) -> JsonInput:
    """Type-narrow ``json_compatible`` for scenario result construction."""

    return cast(JsonInput, json_compatible(value))
