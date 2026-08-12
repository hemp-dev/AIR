"""Statistics and neutral reports for live benchmark result envelopes."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import cast

from .live_models import LiveBenchmarkResult, LiveCallRecord, statistics_for
from .models import BenchmarkMode

LIVE_METRICS = (
    "source_context_bytes",
    "coordination_bytes",
    "request_bytes",
    "materialized_context_bytes",
    "artifact_bytes",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
    "model_calls",
    "preprocessing_seconds",
    "total_model_seconds",
    "provider_seconds",
    "wall_latency_seconds",
    "unique_logical_context_bytes",
    "context_duplication_ratio",
    "call_amplification",
    "air_verifier_seconds",
    "air_verifier_overhead_ratio",
    "unauthorized_attempts",
    "unauthorized_executions",
    "trust_violations",
    "verification_failures",
    "retries",
)


def aggregate_live_results(results: tuple[LiveBenchmarkResult, ...]) -> dict[str, object]:
    grouped: dict[tuple[str, BenchmarkMode], list[LiveBenchmarkResult]] = defaultdict(list)
    for result in results:
        grouped[(result.scenario, result.mode)].append(result)
    rows = [
        _aggregate_row(scenario, mode, records)
        for (scenario, mode), records in sorted(
            grouped.items(), key=lambda item: (item[0][0], item[0][1].value)
        )
    ]
    return {
        "agent_rows": _aggregate_agent_rows(results),
        "deltas": _deltas(rows),
        "rows": rows,
        "scale_series": _scale_series(rows),
    }


def _aggregate_agent_rows(results: tuple[LiveBenchmarkResult, ...]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[LiveCallRecord]] = defaultdict(list)
    for result in results:
        for call in result.calls:
            grouped[(result.scenario, result.mode.value, call.logical_agent)].append(call)
    rows: list[dict[str, object]] = []
    metrics = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "request_bytes",
        "communication_bytes",
        "materialized_context_bytes",
        "preprocessing_seconds",
        "provider_seconds",
        "total_seconds",
        "retry_count",
    )
    for (scenario, mode, logical_agent), calls in sorted(grouped.items()):
        row: dict[str, object] = {
            "logical_agent": logical_agent,
            "mode": mode,
            "provider": calls[0].provider,
            "scenario": scenario,
            "invocations": len(calls),
        }
        for metric in metrics:
            values = [_call_metric_value(call, metric) for call in calls]
            numeric = [value for value in values if isinstance(value, (int, float))]
            row[metric] = statistics_for([float(value) for value in numeric])
            row[f"{metric}_available"] = len(numeric)
        rows.append(row)
    return rows


def _call_metric_value(call: LiveCallRecord, metric: str) -> float | int | None:
    if metric == "total_tokens":
        if call.input_tokens is None or call.output_tokens is None:
            return None
        return call.input_tokens + call.output_tokens
    value = getattr(call, metric)
    return value if isinstance(value, (int, float)) else None


def _aggregate_row(
    scenario: str,
    mode: BenchmarkMode,
    records: list[LiveBenchmarkResult],
) -> dict[str, object]:
    row: dict[str, object] = {
        "fixture_ids": sorted({record.fixture.fixture_id for record in records}),
        "mode": mode.value,
        "repetitions": len(records),
        "scenario": scenario,
        "success_rate": sum(1 for record in records if record.success) / len(records),
    }
    for metric in LIVE_METRICS:
        values = [_metric_value(record, metric) for record in records]
        numeric = [value for value in values if isinstance(value, (int, float))]
        row[metric] = statistics_for([float(value) for value in numeric])
        row[f"{metric}_available"] = len(numeric)
    return row


def _deltas(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(str(row["scenario"]), str(row["mode"])): row for row in rows}
    comparisons = (
        (BenchmarkMode.NL, BenchmarkMode.JSON),
        (BenchmarkMode.JSON, BenchmarkMode.SJSON),
        (BenchmarkMode.SJSON, BenchmarkMode.AIR),
    )
    metrics = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "materialized_context_bytes",
        "coordination_bytes",
        "wall_latency_seconds",
        "model_calls",
        "air_verifier_seconds",
    )
    deltas: list[dict[str, object]] = []
    scenarios = sorted({str(row["scenario"]) for row in rows})
    for scenario in scenarios:
        for from_mode, to_mode in comparisons:
            baseline = by_key.get((scenario, from_mode.value))
            candidate = by_key.get((scenario, to_mode.value))
            if baseline is None or candidate is None:
                continue
            for metric in metrics:
                baseline_median = _median_from_row(baseline, metric)
                candidate_median = _median_from_row(candidate, metric)
                deltas.append(
                    {
                        "baseline_median": baseline_median,
                        "candidate_median": candidate_median,
                        "comparison": f"{from_mode.value}->{to_mode.value}",
                        "metric": metric,
                        "relative_improvement": _relative_improvement(
                            baseline_median, candidate_median
                        ),
                        "scenario": scenario,
                    }
                )
    return deltas


def _scale_series(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    series: list[dict[str, object]] = []
    for row in rows:
        scenario = str(row["scenario"])
        if "." not in scenario:
            continue
        family, scale = scenario.rsplit(".", 1)
        series.append(
            {
                "family": family,
                "mode": row["mode"],
                "scale": scale,
                "scenario": scenario,
                "input_tokens": row["input_tokens"],
                "materialized_context_bytes": row["materialized_context_bytes"],
                "source_context_bytes": row["source_context_bytes"],
                "wall_latency_seconds": row["wall_latency_seconds"],
            }
        )
    return series


def _metric_value(result: LiveBenchmarkResult, metric: str) -> float | int | None:
    if metric == "model_calls":
        return len(result.calls)
    if metric == "total_tokens":
        return result.total_tokens
    if metric == "context_duplication_ratio":
        return result.context_duplication_ratio
    if metric == "call_amplification":
        return result.call_amplification
    if metric == "air_verifier_overhead_ratio":
        return result.air_verifier_overhead_ratio
    value = getattr(result, metric)
    return value if isinstance(value, (int, float)) else None


def _median_from_row(row: Mapping[str, object], metric: str) -> float | None:
    stats = row.get(metric)
    if not isinstance(stats, Mapping):
        return None
    value = stats.get("median")
    return float(value) if isinstance(value, (int, float)) else None


def _relative_improvement(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return 1 - candidate / baseline


def live_markdown(
    *,
    profile: Mapping[str, object],
    aggregate: Mapping[str, object],
    results: Iterable[object] = (),
    limitations: str = (
        "Live measurements cover one provider/model configuration and are not "
        "evidence about all models. Provider caching and service load may vary."
    ),
) -> str:
    rows = cast(list[Mapping[str, object]], aggregate.get("rows", []))
    deltas = cast(list[Mapping[str, object]], aggregate.get("deltas", []))
    lines = [
        "# AIR Live Benchmark Report",
        "",
        "## Experiment Configuration",
        "",
        "```json",
        json.dumps(dict(profile), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Correctness",
        "",
        _success_table(rows),
        "",
        "## Context Scaling",
        "",
        _series_table(aggregate.get("scale_series", [])),
        "",
        "## Token Usage",
        "",
        _metric_table(rows, "input_tokens", "Input tokens"),
        "",
        "## Model Calls",
        "",
        _metric_table(rows, "model_calls", "Model calls"),
        "",
        _agent_table(aggregate.get("agent_rows", [])),
        "",
        "## Latency",
        "",
        _metric_table(rows, "wall_latency_seconds", "Median wall latency (s)"),
        "",
        "## Shared-State Gain",
        "",
        _delta_table(deltas, "JSON->SJSON"),
        "",
        "## AIR Incremental Gain",
        "",
        _delta_table(deltas, "SJSON->AIR"),
        "",
        "## Security",
        "",
        _security_table(rows),
        "",
        "## Runtime Overhead",
        "",
        _metric_table(rows, "air_verifier_seconds", "AIR verifier/runtime seconds"),
        "",
        "## Limitations",
        "",
        limitations,
        "",
        "## Interpretation",
        "",
        "Comparisons are paired by fixture identity. A positive relative improvement "
        "is descriptive for the reported metric; it is not a universal claim. "
        "Raw provider usage remains authoritative and nullable when unavailable.",
    ]
    del results
    return "\n".join(lines) + "\n"


def _success_table(rows: list[Mapping[str, object]]) -> str:
    lines = [
        "| Scenario | Mode | Success rate | Input tok | Output tok | Context bytes | "
        "Calls | Median latency |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {mode} | {success} | {input} | {output} | {context} | "
            "{calls} | {latency} |".format(
                scenario=row.get("scenario", "—"),
                mode=row.get("mode", "—"),
                success=_display(row.get("success_rate")),
                input=_stat_display(row, "input_tokens"),
                output=_stat_display(row, "output_tokens"),
                context=_stat_display(row, "materialized_context_bytes"),
                calls=_stat_display(row, "model_calls"),
                latency=_stat_display(row, "wall_latency_seconds"),
            )
        )
    return "\n".join(lines)


def _metric_table(rows: list[Mapping[str, object]], metric: str, title: str) -> str:
    lines = [
        "| Scenario | Mode | Metric | Median | Mean | Min | Max |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        stats = row.get(metric)
        if not isinstance(stats, Mapping):
            continue
        lines.append(
            f"| {row.get('scenario', '—')} | {row.get('mode', '—')} | {title} | "
            f"{_display(stats.get('median'))} | {_display(stats.get('mean'))} | "
            f"{_display(stats.get('min'))} | {_display(stats.get('max'))} |"
        )
    return "\n".join(lines)


def _agent_table(value: object) -> str:
    rows = value if isinstance(value, list) else []
    lines = [
        "| Scenario | Mode | Logical agent | Invocations | Input tok | Output tok | Total tok |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"| {row.get('scenario', '—')} | {row.get('mode', '—')} | "
            f"{row.get('logical_agent', '—')} | {row.get('invocations', '—')} | "
            f"{_nested_display(row.get('input_tokens'))} | "
            f"{_nested_display(row.get('output_tokens'))} | "
            f"{_nested_display(row.get('total_tokens'))} |"
        )
    return "\n".join(lines)


def _delta_table(deltas: list[Mapping[str, object]], comparison: str) -> str:
    lines = [
        "| Scenario | Metric | Baseline median | Candidate median | Relative improvement |",
        "|---|---|---:|---:|---:|",
    ]
    for delta in deltas:
        if delta.get("comparison") != comparison:
            continue
        lines.append(
            f"| {delta.get('scenario', '—')} | {delta.get('metric', '—')} | "
            f"{_display(delta.get('baseline_median'))} | "
            f"{_display(delta.get('candidate_median'))} | "
            f"{_display(delta.get('relative_improvement'))} |"
        )
    return "\n".join(lines)


def _series_table(series: object) -> str:
    values = series if isinstance(series, list) else []
    lines = [
        "| Scenario | Mode | Scale | Source bytes median | Input tokens median | "
        "Context bytes median | Latency median (s) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for item in values:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| {item.get('scenario', '—')} | {item.get('mode', '—')} | {item.get('scale', '—')} | "
            f"{_nested_display(item.get('source_context_bytes'))} | "
            f"{_nested_display(item.get('input_tokens'))} | "
            f"{_nested_display(item.get('materialized_context_bytes'))} | "
            f"{_nested_display(item.get('wall_latency_seconds'))} |"
        )
    return "\n".join(lines)


def _security_table(rows: list[Mapping[str, object]]) -> str:
    lines = [
        "| Scenario | Mode | Attempts | Executions | Trust violations | Verification failures |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('scenario', '—')} | {row.get('mode', '—')} | "
            f"{_stat_display(row, 'unauthorized_attempts')} | "
            f"{_stat_display(row, 'unauthorized_executions')} | "
            f"{_stat_display(row, 'trust_violations')} | "
            f"{_stat_display(row, 'verification_failures')} |"
        )
    return "\n".join(lines)


def _stat_display(row: Mapping[str, object], metric: str) -> str:
    stats = row.get(metric)
    if not isinstance(stats, Mapping):
        return "—"
    return _display(stats.get("median"))


def _nested_display(value: object) -> str:
    if not isinstance(value, Mapping):
        return "—"
    return _display(value.get("median"))


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
