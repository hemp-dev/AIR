from dataclasses import replace

import pytest

from air.bench import (
    BenchmarkEquivalenceError,
    BenchmarkMode,
    BenchmarkRunner,
    NoopTokenCounter,
    aggregate_results,
    scenario_cases,
    select_scenarios,
    serialize_raw_results,
)


def _by_mode(scenario: str):
    case = select_scenarios(scenario, "full")[0]
    return {mode: case.run(mode, 1, NoopTokenCounter()) for mode in BenchmarkMode}


@pytest.mark.parametrize("case", scenario_cases(), ids=lambda item: item.name)
def test_all_required_scenarios_are_semantically_equivalent(case) -> None:
    executions = {mode: case.run(mode, 1, NoopTokenCounter()) for mode in BenchmarkMode}
    assert all(execution.success for execution in executions.values())
    expected = next(iter(executions.values())).expected_result
    assert all(execution.actual_result == expected for execution in executions.values())


def test_smoke_runner_executes_all_modes_and_enforces_equivalence() -> None:
    results = BenchmarkRunner().run()

    assert len(results) == len(select_scenarios(None, "smoke")) * len(BenchmarkMode)
    assert all(result.success for result in results)
    BenchmarkRunner.assert_semantic_equivalence(results)


def test_fixture_contract_is_explicit_for_each_scenario() -> None:
    for case in scenario_cases():
        assert case.input_semantics
        assert case.expected_output is not None


def test_equivalence_gate_reports_a_divergent_mode() -> None:
    results = BenchmarkRunner().run(scenario="information-relay")
    broken = replace(results[0], actual_result={"wrong": True}, success=False)

    with pytest.raises(BenchmarkEquivalenceError):
        BenchmarkRunner.assert_semantic_equivalence((broken, *results[1:]))


def test_long_context_projection_reduces_materialized_context() -> None:
    results = _by_mode("long-context.small")
    materialized = {
        mode: execution.metrics.materialized_context_bytes for mode, execution in results.items()
    }

    assert materialized[BenchmarkMode.SJSON] < materialized[BenchmarkMode.JSON]
    assert materialized[BenchmarkMode.AIR] == materialized[BenchmarkMode.SJSON]
    assert materialized[BenchmarkMode.JSON] >= materialized[BenchmarkMode.NL]


def test_shared_edit_conflict_is_detected_without_lost_update() -> None:
    results = _by_mode("shared-edit.conflict")

    for mode in (BenchmarkMode.SJSON, BenchmarkMode.AIR):
        execution = results[mode]
        assert execution.success
        assert execution.actual_result == {"left": 1, "right": 0}
        assert execution.metrics.state_conflict_count == 1
        assert execution.metrics.unauthorized_executions == 0


def test_security_scenario_executes_no_unauthorized_effect() -> None:
    results = _by_mode("security-taint")

    for execution in results.values():
        assert execution.success
        assert execution.actual_result == {"approved": False}
        assert execution.metrics.unauthorized_attempts == 1
        assert execution.metrics.unauthorized_executions == 0
    assert results[BenchmarkMode.AIR].metrics.verification_failures == 1


def test_raw_serialization_and_aggregate_keep_nullable_metrics() -> None:
    results = BenchmarkRunner().run(scenario="information-relay")
    raw = serialize_raw_results(results)
    aggregate = aggregate_results(results)

    assert raw == serialize_raw_results(results)
    assert '"input_tokens":null' in raw
    assert len(aggregate.rows) == len(BenchmarkMode)
    assert any(
        delta["from_mode"] == "JSON" and delta["to_mode"] == "SJSON" for delta in aggregate.deltas
    )
    assert any(
        delta["from_mode"] == "SJSON" and delta["to_mode"] == "AIR" for delta in aggregate.deltas
    )
