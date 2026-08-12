"""Command-line entry point for the deterministic AIR benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from ..ir import JsonInput
from .adapters import ModelAdapterError, OpenAIResponsesAdapter
from .live_models import ExperimentProfile, PricingProfile
from .live_report import live_markdown
from .live_runner import LiveBenchmarkRunner
from .models import BENCHMARK_VERSION, BenchmarkMode
from .report import aggregate_results
from .runner import BenchmarkRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline AIR benchmark harness")
    parser.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    parser.add_argument(
        "--variants",
        "--modes",
        dest="variants",
        default="NL,JSON,SJSON,AIR",
        help="comma-separated execution modes (default: NL,JSON,SJSON,AIR)",
    )
    parser.add_argument(
        "--scenario",
        help="run one scenario or a scenario family prefix instead of the suite",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", type=Path, help="write the report to this path")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="report format (JSON includes raw records and aggregates)",
    )
    return parser


def build_live_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m air.bench live",
        description="Run an explicitly opt-in real-model AIR benchmark",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        required=True,
        help="required acknowledgement that provider calls may incur cost",
    )
    parser.add_argument("--provider", choices=("openai",), default="openai")
    parser.add_argument("--model", default=os.environ.get("AIR_BENCH_MODEL"))
    parser.add_argument("--variants", default="NL,JSON,SJSON,AIR")
    parser.add_argument(
        "--scenario",
        choices=("long-context", "relay", "fanout", "adversarial-trust"),
    )
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmup-runs", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--no-randomize", action="store_true")
    parser.add_argument("--context-sizes", default="small")
    parser.add_argument("--relay-depths", default="2")
    parser.add_argument("--fanout-widths", default="2")
    parser.add_argument("--output", type=Path, help="write the live report to this path")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--cached-input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "live":
        return _live_main(arguments[1:])
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        modes = BenchmarkMode.parse_many(args.variants)
        results = BenchmarkRunner().run(
            suite=args.suite,
            modes=modes,
            scenario=args.scenario,
            repeats=args.repeats,
            seed=args.seed,
        )
    except ValueError as exc:
        parser.error(str(exc))

    aggregate = aggregate_results(results)
    if args.format == "markdown":
        output = aggregate.to_markdown()
    else:
        payload = {
            "aggregate": aggregate.to_json_obj(),
            "benchmark_version": BENCHMARK_VERSION,
            "results": [result.to_json_obj() for result in results],
            "suite": args.suite,
            "variants": [mode.value for mode in modes],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return 0


def _live_main(argv: Sequence[str]) -> int:
    parser = build_live_parser()
    args = parser.parse_args(argv)
    if not args.model:
        parser.error("--model or AIR_BENCH_MODEL is required")
    try:
        modes = BenchmarkMode.parse_many(args.variants)
        pricing = _pricing_from_args(args)
        scenario_parameters: dict[str, JsonInput] = {
            "context_sizes": cast(JsonInput, _csv_strings(args.context_sizes)),
            "relay_depths": cast(JsonInput, _csv_ints(args.relay_depths)),
            "fanout_widths": cast(JsonInput, _csv_ints(args.fanout_widths)),
        }
        profile = ExperimentProfile(
            provider=args.provider,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            repetitions=args.repetitions,
            warmup_runs=args.warmup_runs,
            timeout_seconds=args.timeout,
            retries=args.retries,
            seed=args.seed,
            randomize_order=not args.no_randomize,
            scenario_parameters=scenario_parameters,
            pricing=pricing,
        )
        adapter = OpenAIResponsesAdapter.from_env(max_retries=args.retries)
        experiment = LiveBenchmarkRunner(adapter).run(
            profile,
            modes=modes,
            scenario=args.scenario,
        )
    except (ModelAdapterError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "markdown":
        output = live_markdown(
            profile=profile.to_json_obj(),
            aggregate=experiment.aggregate,
            results=experiment.results,
        )
    else:
        output = (
            json.dumps(experiment.to_json_obj(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
    if args.output is None:
        print(output, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return 0


def _csv_strings(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("at least one string parameter is required")
    return values


def _csv_ints(raw: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(f"invalid integer parameter list: {raw!r}") from exc
    if not values or any(value < 1 for value in values):
        raise ValueError("integer parameter list must contain positive values")
    return values


def _pricing_from_args(args: argparse.Namespace) -> PricingProfile | None:
    values = (
        args.input_price_per_million,
        args.cached_input_price_per_million,
        args.output_price_per_million,
    )
    if all(value is None for value in values):
        return None
    return PricingProfile(
        name="cli",
        input_price_per_million=args.input_price_per_million,
        cached_input_price_per_million=args.cached_input_price_per_million,
        output_price_per_million=args.output_price_per_million,
        source="CLI arguments",
    )


if __name__ == "__main__":
    raise SystemExit(main())
