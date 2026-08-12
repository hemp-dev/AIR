"""Offline deterministic benchmark harness for AIR v0.1."""

from .adapters import (
    HttpTransport,
    ModelAdapterError,
    OpenAIResponsesAdapter,
    TransportResponse,
    UrllibTransport,
)
from .ledger import (
    CommunicationLedger,
    CommunicationRecord,
    ContextMaterialization,
    MetricsCollector,
)
from .live_ledger import LiveLedgerTotals, ModelCallLedger
from .live_models import (
    ExperimentProfile,
    LiveBenchmarkResult,
    LiveCallRecord,
    LiveExperiment,
    LiveFixture,
    LiveScenarioOutcome,
    ModelAdapter,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PricingBreakdown,
    PricingProfile,
    calculate_pricing,
    fixture_hash,
    statistics_for,
)
from .live_report import aggregate_live_results, live_markdown
from .live_runner import LiveBenchmarkRunner
from .live_scenarios import LiveScenarioCase, live_scenario_cases, select_live_scenarios
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
    "ExperimentProfile",
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
    "HttpTransport",
    "LiveBenchmarkResult",
    "LiveBenchmarkRunner",
    "LiveCallRecord",
    "LiveExperiment",
    "LiveFixture",
    "LiveLedgerTotals",
    "LiveScenarioCase",
    "LiveScenarioOutcome",
    "MetricsCollector",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelCallLedger",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "NoopTokenCounter",
    "OpenAIResponsesAdapter",
    "PricingBreakdown",
    "PricingProfile",
    "ScenarioCase",
    "ScenarioExecution",
    "TokenCounter",
    "TransportResponse",
    "UrllibTransport",
    "aggregate_live_results",
    "aggregate_results",
    "calculate_pricing",
    "fixture_hash",
    "live_markdown",
    "live_scenario_cases",
    "scenario_cases",
    "select_live_scenarios",
    "select_scenarios",
    "serialize_raw_results",
    "statistics_for",
]
