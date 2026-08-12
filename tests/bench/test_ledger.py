from air.bench import CommunicationLedger, FunctionTokenCounter, NoopTokenCounter
from air.bench.models import canonical_bytes


def test_ledger_separates_transport_and_context_materialization() -> None:
    ledger = CommunicationLedger(NoopTokenCounter())
    payload = {"b": 2, "a": 1, "irrelevant": "x" * 64}

    assert ledger.record_source_context(payload) == len(canonical_bytes(payload))
    record = ledger.send(
        "agent://a",
        "agent://b",
        "json.message",
        {"state_ref": "wm://fixture#v1"},
        logical_content_id="fixture.ref",
    )
    materialization = ledger.materialize(
        "agent://b",
        "wm://fixture#v1",
        {"answer": 713},
        reason="requested projection",
    )

    assert record.payload_size_bytes < ledger.source_context_bytes
    assert ledger.serialized_message_bytes == record.payload_size_bytes
    assert ledger.materialized_context_bytes == materialization.bytes
    assert ledger.input_tokens is None
    assert ledger.output_tokens is None
    assert record.logical_content_id == "fixture.ref"
    assert materialization.source_ref == "wm://fixture#v1"


def test_ledger_accepts_an_explicit_exact_token_counter() -> None:
    counter = FunctionTokenCounter(
        lambda text, _model: len(text.split()), profile="word-test", exact=True
    )
    ledger = CommunicationLedger(counter)
    ledger.send("a", "b", "text", "one two", logical_content_id="text")
    ledger.materialize("b", "text", "three four", reason="test")

    assert ledger.output_tokens == 2
    assert ledger.input_tokens == 2
