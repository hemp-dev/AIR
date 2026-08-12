"""Raw JSON and aggregate Markdown/JSON reporting for benchmark runs."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TypeGuard, cast

from .models import BENCHMARK_VERSION, BenchmarkMode, BenchmarkResult

METRIC_DIRECTIONS: dict[str, str] = {
    "artifact_bytes": "lower",
    "coordination_bytes": "lower",
    "materialized_context_bytes": "lower",
    "serialized_message_bytes": "lower",
    "message_count": "lower",
    "operation_count": "lower",
    "agent_invocation_count": "lower",
    "tool_invocation_count": "lower",
    "state_conflict_count": "lower",
    "unauthorized_executions": "lower",
    "verification_failures": "lower",
    "provenance_coverage": "higher",
    "semantic_score": "higher",
}


def serialize_raw_results(results: tuple[BenchmarkResult, ...] | list[BenchmarkResult]) -> str:
    """Serialize raw records without losing nullable measurements."""

    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "results": [result.to_json_obj() for result in results],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class AggregateReport:
    """Mode summaries plus separately attributable pairwise deltas."""

    rows: tuple[dict[str, object], ...]
    deltas: tuple[dict[str, object], ...]

    def to_json_obj(self) -> dict[str, object]:
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "deltas": list(self.deltas),
            "rows": list(self.rows),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_json_obj(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def to_markdown(self) -> str:
        lines = [
            "# AIR Benchmark Report",
            "",
            "Raw measurements are grouped by scenario and mode. Token fields are",
            "shown as `—` when no exact tokenizer was configured.",
            "",
            "| Scenario | Mode | Success | Coordination bytes | Materialized bytes | "
            "Artifact bytes | Messages | Operations | Input tokens | Security executions |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in self.rows:
            lines.append(
                "| {scenario} | {mode} | {success} | {coordination_bytes} | "
                "{materialized_context_bytes} | {artifact_bytes} | {message_count} | "
                "{operation_count} | "
                "{input_tokens} | {unauthorized_executions} |".format(**_display_row(row))
            )
        lines.extend(
            [
                "",
                "## Attributable deltas",
                "",
                "Each pair is reported separately; no single overall AIR savings "
                "number is computed.",
                "",
                "| Scenario | From | To | Metric | Baseline | Candidate | "
                "Improvement | Direction |",
                "|---|---|---|---|---:|---:|---:|---|",
            ]
        )
        for delta in self.deltas:
            lines.append(
                "| {scenario} | {from_mode} | {to_mode} | {metric} | {baseline} | "
                "{candidate} | {improvement} | {direction} |".format(**_display_delta(delta))
            )
        return "\n".join(lines) + "\n"


def aggregate_results(
    results: tuple[BenchmarkResult, ...] | list[BenchmarkResult],
) -> AggregateReport:
    """Average numeric raw metrics per scenario/mode and compute pairwise deltas."""

    grouped: dict[tuple[str, BenchmarkMode], list[BenchmarkResult]] = defaultdict(list)
    for result in results:
        grouped[(result.scenario, result.mode)].append(result)
    rows: list[dict[str, object]] = []
    for (scenario, mode), records in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        rows.append(_aggregate_row(scenario, mode, records))
    deltas = _compute_deltas(rows)
    return AggregateReport(tuple(rows), tuple(deltas))


def _aggregate_row(
    scenario: str, mode: BenchmarkMode, records: list[BenchmarkResult]
) -> dict[str, object]:
    metrics = records[0].metrics
    row: dict[str, object] = {
        "scenario": scenario,
        "mode": mode.value,
        "success_rate": sum(1 for record in records if record.success) / len(records),
    }
    for field_name in metrics.__dataclass_fields__:
        values = [getattr(record.metrics, field_name) for record in records]
        numeric = [
            value
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        row[field_name] = (
            sum(numeric) / len(numeric) if numeric and len(numeric) == len(values) else None
        )
    row["semantic_score"] = sum(record.semantic_score for record in records) / len(records)
    return row


def _compute_deltas(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(cast(str, row["scenario"]), cast(str, row["mode"])): row for row in rows}
    pairs = (
        (BenchmarkMode.NL, BenchmarkMode.JSON),
        (BenchmarkMode.JSON, BenchmarkMode.SJSON),
        (BenchmarkMode.SJSON, BenchmarkMode.AIR),
    )
    deltas: list[dict[str, object]] = []
    scenarios = sorted({cast(str, row["scenario"]) for row in rows})
    for scenario in scenarios:
        for from_mode, to_mode in pairs:
            baseline = by_key.get((scenario, from_mode.value))
            candidate = by_key.get((scenario, to_mode.value))
            if baseline is None or candidate is None:
                continue
            for metric, direction in METRIC_DIRECTIONS.items():
                baseline_value = baseline.get(metric)
                candidate_value = candidate.get(metric)
                if not _number(baseline_value) or not _number(candidate_value):
                    continue
                baseline_number = baseline_value
                candidate_number = candidate_value
                improvement = (
                    1 - float(candidate_number) / float(baseline_number)
                    if direction == "lower" and float(baseline_number) != 0
                    else (
                        float(candidate_number) / float(baseline_number) - 1
                        if direction == "higher" and float(baseline_number) != 0
                        else None
                    )
                )
                deltas.append(
                    {
                        "scenario": scenario,
                        "from_mode": from_mode.value,
                        "to_mode": to_mode.value,
                        "metric": metric,
                        "baseline": baseline_value,
                        "candidate": candidate_value,
                        "improvement": improvement,
                        "direction": direction,
                    }
                )
    return deltas


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _display_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "scenario": row["scenario"],
        "mode": row["mode"],
        "success": f"{cast(float, row.get('success_rate', 0.0)):.2f}",
        "coordination_bytes": _display(row.get("coordination_bytes")),
        "materialized_context_bytes": _display(row.get("materialized_context_bytes")),
        "artifact_bytes": _display(row.get("artifact_bytes")),
        "message_count": _display(row.get("message_count")),
        "operation_count": _display(row.get("operation_count")),
        "input_tokens": _display(row.get("input_tokens")),
        "unauthorized_executions": _display(row.get("unauthorized_executions")),
    }


def _display_delta(delta: dict[str, object]) -> dict[str, object]:
    return {
        key: _display(value) if key in {"baseline", "candidate", "improvement"} else value
        for key, value in delta.items()
    }


def _display(value: object) -> object:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return value
