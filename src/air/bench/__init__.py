"""Offline deterministic benchmark harness for AIR v0.1."""

from .ledger import (
    CommunicationLedger,
    CommunicationRecord,
    ContextMaterialization,
    MetricsCollector,
)
from .models import (
    BENCHMARK_VERSION,
    BenchmarkEquivalenceError,
    BenchmarkMetrics,
    BenchmarkMode,
    BenchmarkResult,
    FunctionTokenCounter,
    NoopTokenCounter,
    ScenarioExecution,
    TokenCounter,
)
from .report import AggregateReport, aggregate_results, serialize_raw_results
from .runner import BenchmarkRunner
from .scenarios import BenchmarkScenario, ScenarioCase, scenario_cases, select_scenarios

__all__ = [
    "BENCHMARK_VERSION",
    "AggregateReport",
    "BenchmarkMetrics",
    "BenchmarkMode",
    "BenchmarkResult",
    "BenchmarkEquivalenceError",
    "BenchmarkRunner",
    "BenchmarkScenario",
    "CommunicationLedger",
    "CommunicationRecord",
    "ContextMaterialization",
    "FunctionTokenCounter",
    "NoopTokenCounter",
    "MetricsCollector",
    "ScenarioCase",
    "ScenarioExecution",
    "TokenCounter",
    "aggregate_results",
    "scenario_cases",
    "select_scenarios",
    "serialize_raw_results",
]
