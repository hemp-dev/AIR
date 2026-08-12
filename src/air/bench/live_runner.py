"""Paired, randomized live experiment runner."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime
from time import perf_counter

from ..ir import AIR_VERSION
from .live_ledger import ModelCallLedger
from .live_models import (
    ExperimentProfile,
    LiveBenchmarkResult,
    LiveExperiment,
    LiveFixture,
    LiveScenarioOutcome,
    ModelAdapter,
    current_commit,
    live_environment,
)
from .live_report import aggregate_live_results
from .live_scenarios import (
    LiveExecutionContext,
    LiveInvocationError,
    LiveScenarioCase,
    select_live_scenarios,
)
from .models import BENCHMARK_VERSION, BenchmarkMode, canonical_bytes


class LiveBenchmarkRunner:
    """Run paired model calls only when explicitly constructed by live CLI/API."""

    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    def run(
        self,
        profile: ExperimentProfile,
        *,
        modes: tuple[BenchmarkMode, ...] = tuple(BenchmarkMode),
        scenario: str | None = None,
    ) -> LiveExperiment:
        if not modes:
            raise ValueError("at least one live benchmark mode is required")
        if self.adapter.provider != profile.provider:
            raise ValueError(
                f"profile provider {profile.provider!r} does not match adapter "
                f"{self.adapter.provider!r}"
            )
        cases = select_live_scenarios(scenario)
        results: list[LiveBenchmarkResult] = []
        experiment_timestamp = _timestamp()
        for case in cases:
            fixtures = case.fixtures(profile, profile.seed)
            for fixture in fixtures:
                for warmup in range(profile.warmup_runs):
                    warmup_order = self._execution_order(
                        profile, modes, fixture.fixture_id, -(warmup + 1)
                    )
                    for warmup_mode in warmup_order:
                        self._run_mode(
                            profile,
                            case,
                            fixture,
                            warmup_mode,
                            -(warmup + 1),
                            warmup_order,
                            experiment_timestamp,
                        )
                for repetition in range(1, profile.repetitions + 1):
                    execution_order = self._execution_order(
                        profile, modes, fixture.fixture_id, repetition
                    )
                    for mode in execution_order:
                        results.append(
                            self._run_mode(
                                profile,
                                case,
                                fixture,
                                mode,
                                repetition,
                                execution_order,
                                experiment_timestamp,
                            )
                        )
        aggregate = aggregate_live_results(tuple(results))
        return LiveExperiment(
            benchmark_version=BENCHMARK_VERSION,
            air_version=AIR_VERSION,
            commit=current_commit(),
            timestamp_utc=experiment_timestamp,
            profile=profile,
            environment=live_environment(self.adapter.provider),
            warmup_runs=profile.warmup_runs,
            results=tuple(results),
            aggregate=aggregate,
        )

    @staticmethod
    def _execution_order(
        profile: ExperimentProfile,
        modes: tuple[BenchmarkMode, ...],
        fixture_id: str,
        repetition: int,
    ) -> tuple[BenchmarkMode, ...]:
        order = list(modes)
        if not profile.randomize_order:
            return tuple(order)
        seed_material = f"{profile.seed}:{fixture_id}:{repetition}".encode()
        order_seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        random.Random(order_seed).shuffle(order)
        return tuple(order)

    def _run_mode(
        self,
        profile: ExperimentProfile,
        case: LiveScenarioCase,
        fixture: LiveFixture,
        mode: BenchmarkMode,
        repetition: int,
        execution_order: tuple[BenchmarkMode, ...],
        timestamp: str,
    ) -> LiveBenchmarkResult:
        run_id = f"live.{fixture.scenario}.{mode.value.lower()}.r{repetition}"
        ledger = ModelCallLedger()
        context = LiveExecutionContext(
            adapter=self.adapter,
            profile=profile,
            fixture=fixture,
            mode=mode,
            repetition=repetition,
            execution_order=execution_order,
            run_id=run_id,
            ledger=ledger,
        )
        started = perf_counter()
        outcome: LiveScenarioOutcome
        try:
            outcome = case.runner(context, fixture)
            failure_reason = outcome.failure_reason
        except LiveInvocationError as exc:
            outcome = LiveScenarioOutcome(
                actual_result=None,
                details={},
                unique_logical_context_bytes=None,
                minimum_logical_calls=1,
                air_verifier_seconds=context.air_verifier_seconds or None,
                failure_reason=str(exc),
            )
            failure_reason = str(exc)
        except Exception as exc:
            outcome = LiveScenarioOutcome(
                actual_result=None,
                details={},
                unique_logical_context_bytes=None,
                minimum_logical_calls=1,
                air_verifier_seconds=context.air_verifier_seconds or None,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
            failure_reason = outcome.failure_reason
        wall_latency = perf_counter() - started
        totals = ledger.totals()
        success = outcome.actual_result == fixture.expected_result and failure_reason is None
        return LiveBenchmarkResult(
            benchmark_version=BENCHMARK_VERSION,
            air_version=AIR_VERSION,
            commit=current_commit(),
            timestamp_utc=timestamp,
            profile=profile,
            scenario=fixture.scenario,
            mode=mode,
            repetition=repetition,
            execution_order=execution_order,
            fixture=fixture,
            success=success,
            semantic_score=1.0 if success else 0.0,
            actual_result=outcome.actual_result,
            calls=ledger.records,
            source_context_bytes=len(canonical_bytes(fixture.input_semantics)),
            coordination_bytes=totals.communication_bytes,
            request_bytes=totals.request_bytes,
            materialized_context_bytes=totals.materialized_context_bytes,
            artifact_bytes=context.air_artifact_bytes or None,
            input_tokens=totals.input_tokens,
            cached_input_tokens=totals.cached_input_tokens,
            output_tokens=totals.output_tokens,
            reasoning_tokens=totals.reasoning_tokens,
            preprocessing_seconds=totals.preprocessing_seconds,
            provider_seconds=totals.provider_seconds,
            total_model_seconds=totals.total_seconds,
            wall_latency_seconds=wall_latency,
            unique_logical_context_bytes=outcome.unique_logical_context_bytes,
            minimum_logical_calls=outcome.minimum_logical_calls,
            air_verifier_seconds=outcome.air_verifier_seconds,
            unauthorized_attempts=outcome.unauthorized_attempts,
            unauthorized_executions=outcome.unauthorized_executions,
            trust_violations=outcome.trust_violations,
            verification_failures=outcome.verification_failures,
            retries=totals.retries,
            details=outcome.details,
            failure_reason=failure_reason,
            pricing=ledger.pricing(profile.pricing),
        )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
