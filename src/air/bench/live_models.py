"""Provider-neutral models for opt-in live AIR benchmark experiments."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import fmean, median, stdev
from typing import Protocol, cast

from ..ir import JsonInput
from .models import BenchmarkMode, canonical_bytes, json_compatible


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """Provider-neutral text message sent to a model adapter."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "developer", "user", "assistant"}:
            raise ValueError(f"unsupported model message role: {self.role!r}")

    def to_json_obj(self) -> dict[str, str]:
        return {"content": self.content, "role": self.role}


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-independent model invocation request."""

    messages: tuple[ModelMessage, ...]
    model: str
    temperature: float | None
    max_output_tokens: int | None
    timeout_seconds: float
    scenario: str
    mode: BenchmarkMode
    logical_agent: str
    fixture_id: str
    metadata: Mapping[str, JsonInput] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("model request requires at least one message")
        if not self.model.strip():
            raise ValueError("model name must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("model timeout must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive when provided")

    def to_json_obj(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "logical_agent": self.logical_agent,
            "max_output_tokens": self.max_output_tokens,
            "messages": [message.to_json_obj() for message in self.messages],
            "metadata": dict(self.metadata),
            "mode": self.mode.value,
            "model": self.model,
            "scenario": self.scenario,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
        }

    @property
    def serialized_bytes(self) -> int:
        return len(canonical_bytes(self.to_json_obj()))


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Normalized provider response with raw provider usage preserved."""

    output: str
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    model: str | None = None
    provider: str | None = None
    request_id: str | None = None
    latency_seconds: float | None = None
    time_to_first_token_seconds: float | None = None
    finish_reason: str | None = None
    provider_metadata: Mapping[str, JsonInput] = field(default_factory=dict)
    retry_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be non-negative or None")
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")

    def to_json_obj(self, *, include_output: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "cached_input_tokens": self.cached_input_tokens,
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "latency_seconds": self.latency_seconds,
            "model": self.model,
            "output_tokens": self.output_tokens,
            "provider": self.provider,
            "provider_metadata": dict(self.provider_metadata),
            "reasoning_tokens": self.reasoning_tokens,
            "request_id": self.request_id,
            "retry_count": self.retry_count,
            "time_to_first_token_seconds": self.time_to_first_token_seconds,
        }
        if include_output:
            result["output"] = self.output
        return result


class ModelAdapter(Protocol):
    """Provider-neutral boundary for one model invocation."""

    @property
    def provider(self) -> str:
        """Stable provider identifier."""

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Perform one model call and normalize its response."""


@dataclass(frozen=True, slots=True)
class PricingProfile:
    """Optional external price card, expressed in currency units per 1M tokens."""

    name: str
    currency: str = "USD"
    input_price_per_million: float | None = None
    cached_input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    source: str | None = None
    effective_date: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "input_price_per_million",
            "cached_input_price_per_million",
            "output_price_per_million",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative or None")

    def to_json_obj(self) -> dict[str, object]:
        return {
            "cached_input_price_per_million": self.cached_input_price_per_million,
            "currency": self.currency,
            "effective_date": self.effective_date,
            "input_price_per_million": self.input_price_per_million,
            "name": self.name,
            "output_price_per_million": self.output_price_per_million,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class PricingBreakdown:
    """Explicit cost calculation that keeps cached and uncached tokens visible."""

    currency: str
    uncached_input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    input_cost: float | None
    cached_input_cost: float | None
    output_cost: float | None
    total_cost: float | None
    profile: PricingProfile

    def to_json_obj(self) -> dict[str, object]:
        return {
            "cached_input_cost": self.cached_input_cost,
            "cached_input_tokens": self.cached_input_tokens,
            "currency": self.currency,
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "output_tokens": self.output_tokens,
            "pricing_profile": self.profile.to_json_obj(),
            "total_cost": self.total_cost,
            "uncached_input_tokens": self.uncached_input_tokens,
        }


@dataclass(frozen=True, slots=True)
class ExperimentProfile:
    """Serializable configuration stamped onto every paired live experiment."""

    provider: str
    model: str
    temperature: float | None = 0.0
    max_output_tokens: int | None = 256
    repetitions: int = 5
    warmup_runs: int = 0
    timeout_seconds: float = 60.0
    retries: int = 0
    seed: int = 1
    randomize_order: bool = True
    scenario_parameters: Mapping[str, JsonInput] = field(default_factory=dict)
    pricing: PricingProfile | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if self.repetitions < 1:
            raise ValueError("repetitions must be positive")
        if self.warmup_runs < 0 or self.retries < 0:
            raise ValueError("warmup_runs and retries must be non-negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive when provided")

    def to_json_obj(self) -> dict[str, object]:
        return {
            "max_output_tokens": self.max_output_tokens,
            "model": self.model,
            "pricing": self.pricing.to_json_obj() if self.pricing is not None else None,
            "provider": self.provider,
            "randomize_order": self.randomize_order,
            "repetitions": self.repetitions,
            "retries": self.retries,
            "scenario_parameters": dict(self.scenario_parameters),
            "seed": self.seed,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "warmup_runs": self.warmup_runs,
        }


@dataclass(frozen=True, slots=True)
class LiveFixture:
    """One fixture generated once and paired across all representation modes."""

    scenario: str
    parameters: Mapping[str, JsonInput]
    input_semantics: JsonInput
    expected_result: JsonInput
    fixture_id: str

    @classmethod
    def create(
        cls,
        scenario: str,
        parameters: Mapping[str, JsonInput],
        input_semantics: JsonInput,
        expected_result: JsonInput,
    ) -> LiveFixture:
        identity = {
            "expected_result": expected_result,
            "input_semantics": input_semantics,
            "parameters": dict(parameters),
            "scenario": scenario,
        }
        fixture_id = hashlib.sha256(canonical_bytes(identity)).hexdigest()
        return cls(scenario, dict(parameters), input_semantics, expected_result, fixture_id)


@dataclass(frozen=True, slots=True)
class LiveScenarioOutcome:
    """Scenario-specific result after all model calls have completed."""

    actual_result: JsonInput
    details: Mapping[str, JsonInput] = field(default_factory=dict)
    unauthorized_attempts: int = 0
    unauthorized_executions: int = 0
    trust_violations: int = 0
    verification_failures: int = 0
    unique_logical_context_bytes: int | None = None
    minimum_logical_calls: int = 1
    air_verifier_seconds: float | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LiveCallRecord:
    """Non-sensitive ledger record for one provider invocation."""

    run_id: str
    scenario: str
    mode: BenchmarkMode
    logical_agent: str
    call_index: int
    model: str
    provider: str
    fixture_id: str
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
    success: bool
    retry_count: int
    request_sha256: str
    output_sha256: str | None
    request_id: str | None = None
    time_to_first_token_seconds: float | None = None
    finish_reason: str | None = None
    failure_reason: str | None = None

    def to_json_obj(self) -> dict[str, object]:
        return {
            "call_index": self.call_index,
            "cached_input_tokens": self.cached_input_tokens,
            "communication_bytes": self.communication_bytes,
            "failure_reason": self.failure_reason,
            "finish_reason": self.finish_reason,
            "fixture_id": self.fixture_id,
            "input_tokens": self.input_tokens,
            "logical_agent": self.logical_agent,
            "materialized_context_bytes": self.materialized_context_bytes,
            "mode": self.mode.value,
            "model": self.model,
            "output_sha256": self.output_sha256,
            "output_tokens": self.output_tokens,
            "preprocessing_seconds": self.preprocessing_seconds,
            "provider": self.provider,
            "provider_seconds": self.provider_seconds,
            "reasoning_tokens": self.reasoning_tokens,
            "request_bytes": self.request_bytes,
            "request_id": self.request_id,
            "request_sha256": self.request_sha256,
            "retry_count": self.retry_count,
            "run_id": self.run_id,
            "scenario": self.scenario,
            "success": self.success,
            "time_to_first_token_seconds": self.time_to_first_token_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True, slots=True)
class LiveBenchmarkResult:
    """Raw paired result for one scenario/mode/repetition."""

    benchmark_version: str
    air_version: str
    commit: str
    timestamp_utc: str
    profile: ExperimentProfile
    scenario: str
    mode: BenchmarkMode
    repetition: int
    execution_order: tuple[BenchmarkMode, ...]
    fixture: LiveFixture
    success: bool
    semantic_score: float
    actual_result: JsonInput
    calls: tuple[LiveCallRecord, ...]
    source_context_bytes: int
    coordination_bytes: int
    request_bytes: int
    materialized_context_bytes: int
    artifact_bytes: int | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    preprocessing_seconds: float | None
    provider_seconds: float | None
    total_model_seconds: float | None
    wall_latency_seconds: float
    unique_logical_context_bytes: int | None
    minimum_logical_calls: int
    air_verifier_seconds: float | None
    unauthorized_attempts: int
    unauthorized_executions: int
    trust_violations: int
    verification_failures: int
    retries: int
    details: Mapping[str, JsonInput] = field(default_factory=dict)
    failure_reason: str | None = None
    pricing: PricingBreakdown | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    @property
    def context_duplication_ratio(self) -> float | None:
        if self.unique_logical_context_bytes in (None, 0):
            return None
        return self.materialized_context_bytes / self.unique_logical_context_bytes

    @property
    def call_amplification(self) -> float | None:
        if self.minimum_logical_calls <= 0:
            return None
        return len(self.calls) / self.minimum_logical_calls

    @property
    def air_verifier_overhead_ratio(self) -> float | None:
        if self.air_verifier_seconds is None or self.wall_latency_seconds <= 0:
            return None
        return self.air_verifier_seconds / self.wall_latency_seconds

    def metrics_json_obj(self) -> dict[str, object]:
        return {
            "air_verifier_overhead_ratio": self.air_verifier_overhead_ratio,
            "air_verifier_seconds": self.air_verifier_seconds,
            "artifact_bytes": self.artifact_bytes,
            "call_amplification": self.call_amplification,
            "cached_input_tokens": self.cached_input_tokens,
            "communication_bytes": self.coordination_bytes,
            "context_duplication_ratio": self.context_duplication_ratio,
            "input_tokens": self.input_tokens,
            "materialized_context_bytes": self.materialized_context_bytes,
            "minimum_logical_calls": self.minimum_logical_calls,
            "model_calls": len(self.calls),
            "output_tokens": self.output_tokens,
            "preprocessing_seconds": self.preprocessing_seconds,
            "reasoning_tokens": self.reasoning_tokens,
            "request_bytes": self.request_bytes,
            "retries": self.retries,
            "source_context_bytes": self.source_context_bytes,
            "total_model_seconds": self.total_model_seconds,
            "total_tokens": self.total_tokens,
            "unique_logical_context_bytes": self.unique_logical_context_bytes,
            "wall_latency_seconds": self.wall_latency_seconds,
        }

    def to_json_obj(self) -> dict[str, object]:
        result: dict[str, object] = {
            "actual_result": self.actual_result,
            "air_version": self.air_version,
            "benchmark_version": self.benchmark_version,
            "calls": [call.to_json_obj() for call in self.calls],
            "commit": self.commit,
            "details": dict(self.details),
            "execution_order": [mode.value for mode in self.execution_order],
            "fixture": {
                "expected_result": self.fixture.expected_result,
                "fixture_id": self.fixture.fixture_id,
                "parameters": dict(self.fixture.parameters),
                "scenario": self.fixture.scenario,
            },
            "mode": self.mode.value,
            "metrics": self.metrics_json_obj(),
            "profile": self.profile.to_json_obj(),
            "repetition": self.repetition,
            "scenario": self.scenario,
            "semantic_score": self.semantic_score,
            "success": self.success,
            "timestamp_utc": self.timestamp_utc,
        }
        if self.failure_reason is not None:
            result["failure_reason"] = self.failure_reason
        if self.pricing is not None:
            result["pricing"] = self.pricing.to_json_obj()
        return result


@dataclass(frozen=True, slots=True)
class LiveExperiment:
    """Complete live experiment envelope with raw records and aggregate report."""

    benchmark_version: str
    air_version: str
    commit: str
    timestamp_utc: str
    profile: ExperimentProfile
    environment: Mapping[str, JsonInput]
    warmup_runs: int
    results: tuple[LiveBenchmarkResult, ...]
    aggregate: Mapping[str, object]

    def to_json_obj(self) -> dict[str, object]:
        return {
            "aggregate": dict(self.aggregate),
            "air_version": self.air_version,
            "benchmark_version": self.benchmark_version,
            "commit": self.commit,
            "environment": dict(self.environment),
            "profile": self.profile.to_json_obj(),
            "results": [result.to_json_obj() for result in self.results],
            "timestamp_utc": self.timestamp_utc,
            "warmup_runs": self.warmup_runs,
        }


def fixture_hash(value: object) -> str:
    """Return a stable identity for an input fixture or logical payload."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def output_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def live_environment(provider: str) -> dict[str, JsonInput]:
    return {
        "platform": platform.platform(),
        "provider": provider,
        "python_version": sys.version.split()[0],
        "token_source": "provider_reported",
    }


def current_commit() -> str:
    """Return an explicit commit identity, or the current Git revision if available."""

    configured = os.environ.get("AIR_BENCH_COMMIT")
    if configured:
        return configured
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    revision = completed.stdout.strip()
    return revision or "unknown"


def statistics_for(values: list[float]) -> dict[str, float | int | None]:
    """Summarize a numeric sample without inventing values for an empty set."""

    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "stdev": None,
            "p95": None,
        }
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered) + 0.999999) - 1))
    return {
        "count": len(values),
        "mean": fmean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "stdev": stdev(values) if len(values) > 1 else None,
        "p95": ordered[p95_index],
    }


def calculate_pricing(
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    profile: PricingProfile,
) -> PricingBreakdown:
    """Calculate an explicitly labelled cost breakdown from provider usage."""

    uncached: int | None = None
    if input_tokens is not None and cached_input_tokens is not None:
        uncached = max(0, input_tokens - cached_input_tokens)
    input_cost = _token_cost(uncached, profile.input_price_per_million)
    cached_cost = _token_cost(cached_input_tokens, profile.cached_input_price_per_million)
    output_cost = _token_cost(output_tokens, profile.output_price_per_million)
    total = (
        None
        if input_cost is None or cached_cost is None or output_cost is None
        else input_cost + cached_cost + output_cost
    )
    return PricingBreakdown(
        currency=profile.currency,
        uncached_input_tokens=uncached,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        input_cost=input_cost,
        cached_input_cost=cached_cost,
        output_cost=output_cost,
        total_cost=total,
        profile=profile,
    )


def _token_cost(tokens: int | None, price_per_million: float | None) -> float | None:
    if tokens is None or price_per_million is None:
        return None
    return tokens / 1_000_000 * price_per_million


def safe_live_json(value: object) -> JsonInput:
    return cast(JsonInput, json_compatible(value))
