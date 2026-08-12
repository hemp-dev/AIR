"""Deterministic benchmark runner with reproducible raw result records."""

from __future__ import annotations

from dataclasses import replace
from time import perf_counter_ns

from .models import (
    BENCHMARK_VERSION,
    BenchmarkEquivalenceError,
    BenchmarkMode,
    BenchmarkResult,
    NoopTokenCounter,
    TokenCounter,
    benchmark_environment,
)
from .scenarios import ScenarioCase, select_scenarios


class BenchmarkRunner:
    """Run the same scenario fixtures through selected representation modes."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self.token_counter = token_counter or NoopTokenCounter()

    def run(
        self,
        *,
        suite: str = "smoke",
        modes: tuple[BenchmarkMode, ...] = tuple(BenchmarkMode),
        scenario: str | None = None,
        repeats: int = 1,
        seed: int = 1,
        enforce_equivalence: bool = True,
    ) -> tuple[BenchmarkResult, ...]:
        """Run selected cases in stable case/mode/repetition order."""

        if repeats < 1:
            raise ValueError("repeats must be positive")
        cases = select_scenarios(scenario, suite)
        results: list[BenchmarkResult] = []
        for repeat in range(repeats):
            repeat_seed = seed + repeat
            for case in cases:
                for mode in modes:
                    results.append(self._run_case(case, mode, suite, repeat, repeat_seed))
        completed = tuple(results)
        if enforce_equivalence and len(modes) > 1:
            self.assert_semantic_equivalence(completed)
        return completed

    @staticmethod
    def assert_semantic_equivalence(results: tuple[BenchmarkResult, ...]) -> None:
        """Reject a deterministic run when any selected mode diverges."""

        groups: dict[tuple[str, str, str, str], list[BenchmarkResult]] = {}
        for result in results:
            key = (
                result.suite,
                result.scenario,
                str(result.config.get("repeat")),
                str(result.config.get("seed")),
            )
            groups.setdefault(key, []).append(result)
        for key, records in groups.items():
            expected = records[0].expected_result
            mismatches = [
                f"{record.mode.value}: actual={record.actual_result!r}"
                for record in records
                if record.actual_result != expected
            ]
            if mismatches:
                raise BenchmarkEquivalenceError(
                    f"semantic equivalence failed for {key}: " + "; ".join(mismatches)
                )

    def run_case(
        self,
        case: ScenarioCase,
        mode: BenchmarkMode,
        *,
        suite: str = "smoke",
        repeat: int = 0,
        seed: int = 1,
    ) -> BenchmarkResult:
        """Run one already-resolved case; useful for API consumers/tests."""

        return self._run_case(case, mode, suite, repeat, seed)

    def _run_case(
        self,
        case: ScenarioCase,
        mode: BenchmarkMode,
        suite: str,
        repeat: int,
        seed: int,
    ) -> BenchmarkResult:
        run_id = f"{suite}.{case.name}.{mode.value.lower()}.r{repeat + 1}.s{seed}"
        started_ns = perf_counter_ns()
        execution = case.run(mode, seed, self.token_counter)
        elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000
        metrics = replace(
            execution.metrics,
            end_to_end_time_ms=elapsed_ms,
            execution_time_ms=execution.metrics.execution_time_ms or elapsed_ms,
        )
        return BenchmarkResult(
            benchmark_version=BENCHMARK_VERSION,
            suite=suite,
            scenario=case.name,
            mode=mode,
            run_id=run_id,
            success=execution.success,
            semantic_score=execution.semantic_score,
            expected_result=execution.expected_result,
            actual_result=execution.actual_result,
            metrics=metrics,
            config={"repeat": repeat, "seed": seed, "suite": suite},
            environment=benchmark_environment(self.token_counter),
            details=execution.details,
            failure_reason=execution.failure_reason,
        )
