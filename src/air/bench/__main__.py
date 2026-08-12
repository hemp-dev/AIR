"""Command-line entry point for the deterministic AIR benchmark."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
