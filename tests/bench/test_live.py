import json
from collections.abc import Mapping

import pytest

from air.bench import (
    BenchmarkMode,
    ExperimentProfile,
    LiveBenchmarkRunner,
    ModelAdapterError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    OpenAIResponsesAdapter,
    PricingProfile,
    TransportResponse,
    aggregate_live_results,
    live_markdown,
    statistics_for,
)
from air.bench.__main__ import main
from air.bench.live_ledger import ModelCallLedger
from air.bench.live_models import LiveCallRecord
from air.bench.models import canonical_bytes


class FakeAdapter:
    provider = "fake"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        action = request.metadata.get("live_action")
        if action == "long_context_answer":
            output = {"answer": 2140}
        elif action == "relay_forward":
            output = {"secret_number": 713}
        elif action == "relay_final":
            output = {"answer": 2140}
        elif action == "fanout_worker":
            worker = str(request.metadata["worker"])
            index = int(worker.rsplit("-", 1)[1])
            output = {"id": worker, "score": (11 + index * 6) * 2 + 1}
        elif action == "fanout_join":
            output = _results_from_join(request.messages[-1].content)
        elif action == "security_proposal":
            output = {"action": "write", "approved": True}
        else:
            raise AssertionError(f"unexpected fake action: {action!r}")
        encoded = json.dumps(output, separators=(",", ":"))
        return ModelResponse(
            output=encoded,
            input_tokens=10 + len(request.messages[-1].content.encode("utf-8")) // 100,
            output_tokens=3,
            cached_input_tokens=2,
            reasoning_tokens=1,
            model=request.model,
            provider=self.provider,
            request_id=f"fake-{len(self.requests)}",
            latency_seconds=0.001,
            finish_reason="completed",
        )


def _results_from_join(content: str) -> list[dict[str, int | str]]:
    start = content.find("[")
    end = content.rfind("]")
    if start < 0 or end <= start:
        raise AssertionError(f"join payload has no result array: {content!r}")
    parsed = json.loads(content[start : end + 1])
    assert isinstance(parsed, list)
    return parsed


def _profile(*, repetitions: int = 2, warmup_runs: int = 0) -> ExperimentProfile:
    return ExperimentProfile(
        provider="fake",
        model="fake-model",
        repetitions=repetitions,
        warmup_runs=warmup_runs,
        scenario_parameters={
            "context_sizes": ["small"],
            "relay_depths": [2],
            "fanout_widths": [2],
        },
    )


def test_live_runner_is_offline_with_fake_adapter_and_pairs_all_scenarios() -> None:
    adapter = FakeAdapter()
    experiment = LiveBenchmarkRunner(adapter).run(_profile())

    assert len(experiment.results) == 4 * len(BenchmarkMode) * 2
    assert all(result.success for result in experiment.results)
    assert len(adapter.requests) == sum(len(result.calls) for result in experiment.results)
    assert len(experiment.aggregate["rows"]) == 4 * len(BenchmarkMode)
    assert experiment.aggregate["agent_rows"]
    assert any(delta["comparison"] == "JSON->SJSON" for delta in experiment.aggregate["deltas"])
    assert all(result.input_tokens is not None for result in experiment.results)
    assert all(result.cached_input_tokens == 2 * len(result.calls) for result in experiment.results)

    by_fixture: dict[str, set[str]] = {}
    for result in experiment.results:
        by_fixture.setdefault(result.scenario, set()).add(result.fixture.fixture_id)
        assert result.calls
        assert result.calls[0].materialized_context_bytes > 0
        assert result.calls[0].request_sha256 != result.calls[0].output_sha256
    assert all(len(fixture_ids) == 1 for fixture_ids in by_fixture.values())
    json.dumps(experiment.to_json_obj())

    markdown = live_markdown(
        profile=experiment.profile.to_json_obj(),
        aggregate=experiment.aggregate,
        results=experiment.results,
    )
    for heading in (
        "Experiment Configuration",
        "Correctness",
        "Context Scaling",
        "Token Usage",
        "Model Calls",
        "Latency",
        "Shared-State Gain",
        "AIR Incremental Gain",
        "Security",
        "Runtime Overhead",
        "Limitations",
        "Interpretation",
    ):
        assert f"## {heading}" in markdown


def test_live_order_is_seeded_and_warmups_are_excluded_from_aggregates() -> None:
    first_adapter = FakeAdapter()
    first = LiveBenchmarkRunner(first_adapter).run(
        _profile(repetitions=2, warmup_runs=1), scenario="long-context"
    )
    second = LiveBenchmarkRunner(FakeAdapter()).run(
        _profile(repetitions=2, warmup_runs=1), scenario="long-context"
    )

    assert len(first.results) == 2 * len(BenchmarkMode)
    assert len(first_adapter.requests) == (1 + 2) * len(BenchmarkMode)
    first_orders = [
        (result.fixture.fixture_id, result.repetition, tuple(result.execution_order))
        for result in first.results
    ]
    second_orders = [
        (result.fixture.fixture_id, result.repetition, tuple(result.execution_order))
        for result in second.results
    ]
    assert first_orders == second_orders
    assert all(row["repetitions"] == 2 for row in first.aggregate["rows"])


def test_live_statistics_and_pricing_are_explicit_and_nullable() -> None:
    assert statistics_for([])["p95"] is None
    stats = statistics_for([1.0, 2.0, 4.0, 8.0])
    assert stats["count"] == 4
    assert stats["median"] == 3.0
    assert stats["min"] == 1.0
    assert stats["max"] == 8.0
    assert stats["p95"] == 8.0

    record = LiveCallRecord(
        run_id="run",
        scenario="scenario",
        mode=BenchmarkMode.JSON,
        logical_agent="agent://a",
        call_index=1,
        model="model",
        provider="fake",
        fixture_id="fixture",
        request_bytes=10,
        communication_bytes=5,
        materialized_context_bytes=8,
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=10,
        reasoning_tokens=2,
        preprocessing_seconds=0.1,
        provider_seconds=0.2,
        total_seconds=0.3,
        success=True,
        retry_count=1,
        request_sha256="request",
        output_sha256="output",
    )
    ledger = ModelCallLedger()
    ledger.append(record)
    pricing = ledger.pricing(
        PricingProfile(
            name="test",
            input_price_per_million=1.0,
            cached_input_price_per_million=0.5,
            output_price_per_million=2.0,
        )
    )
    assert pricing is not None
    assert pricing.uncached_input_tokens == 80
    assert pricing.cached_input_tokens == 20
    assert pricing.output_tokens == 10
    assert pricing.total_cost == pytest.approx(0.00011)


class FakeTransport:
    def __init__(self, responses: list[TransportResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, str], bytes, float]] = []

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        self.calls.append((url, headers, body, timeout_seconds))
        return self.responses.pop(0)


def _request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage("user", "Return JSON."),),
        model="gpt-test",
        temperature=0.0,
        max_output_tokens=32,
        timeout_seconds=3.0,
        scenario="test",
        mode=BenchmarkMode.JSON,
        logical_agent="agent://test",
        fixture_id="fixture",
    )


def test_openai_adapter_normalizes_usage_and_retries_without_network() -> None:
    success = TransportResponse(
        status_code=200,
        headers={"x-request-id": "header-request"},
        body=json.dumps(
            {
                "id": "response-id",
                "model": "gpt-test",
                "status": "completed",
                "output_text": '{"answer": 2140}',
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
            }
        ).encode(),
    )
    transport = FakeTransport([TransportResponse(429, {}, b"busy"), success])
    adapter = OpenAIResponsesAdapter(
        "secret-key",
        max_retries=1,
        transport=transport,
        sleep=lambda _seconds: None,
    )

    response = adapter.invoke(_request())

    assert response.input_tokens == 11
    assert response.cached_input_tokens == 2
    assert response.output_tokens == 4
    assert response.reasoning_tokens == 1
    assert response.request_id == "header-request"
    assert response.retry_count == 1
    assert response.provider_metadata["usage"] == {
        "input_tokens": 11,
        "output_tokens": 4,
        "input_tokens_details": {"cached_tokens": 2},
        "output_tokens_details": {"reasoning_tokens": 1},
    }
    assert len(transport.calls) == 2
    assert transport.calls[0][1]["Authorization"] == "Bearer secret-key"
    assert b"secret-key" not in transport.calls[0][2]
    assert "secret-key" not in json.dumps(response.to_json_obj())


def test_openai_adapter_requires_key_and_records_failed_retries() -> None:
    with pytest.raises(ModelAdapterError, match="OPENAI_API_KEY"):
        OpenAIResponsesAdapter.from_env(transport=FakeTransport([]))

    transport = FakeTransport([TransportResponse(503, {}, b"down")])
    adapter = OpenAIResponsesAdapter(
        "secret-key",
        transport=transport,
        max_retries=0,
    )
    with pytest.raises(ModelAdapterError) as raised:
        adapter.invoke(_request())
    assert raised.value.status_code == 503
    assert raised.value.retry_count == 0


def test_live_cli_requires_explicit_execution_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as missing_ack:
        main(["live", "--model", "gpt-test"])
    assert missing_ack.value.code == 2

    with pytest.raises(SystemExit) as missing_key:
        main(["live", "--execute", "--model", "gpt-test"])
    assert missing_key.value.code == 2


def test_live_aggregate_is_stable_for_same_raw_records() -> None:
    experiment = LiveBenchmarkRunner(FakeAdapter()).run(
        _profile(repetitions=1), scenario="long-context"
    )
    assert aggregate_live_results(experiment.results) == experiment.aggregate
    assert canonical_bytes(experiment.aggregate) == canonical_bytes(
        aggregate_live_results(experiment.results)
    )
