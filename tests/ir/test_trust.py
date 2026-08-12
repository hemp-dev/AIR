from datetime import UTC, datetime

from air.ir import (
    ActorRef,
    OpId,
    Provenance,
    ResultId,
    TrustLabel,
    ValueRef,
    trust_transition_allowed,
)


def test_trust_labels_are_explicit_strings_not_an_implicit_ranking() -> None:
    assert [label.value for label in TrustLabel] == [
        "Verified",
        "SystemDerived",
        "AgentDerived",
        "UserSupplied",
        "ExternalUntrusted",
        "Unknown",
    ]
    assert not trust_transition_allowed(TrustLabel.EXTERNAL_UNTRUSTED, TrustLabel.VERIFIED)
    assert trust_transition_allowed(
        TrustLabel.EXTERNAL_UNTRUSTED,
        TrustLabel.VERIFIED,
        explicit_verification=True,
    )


def test_provenance_is_immutable_and_serializes_refs_deterministically() -> None:
    provenance = Provenance(
        source_refs=("wm://case/input#v1", ValueRef(ResultId("%source"))),
        produced_by=ActorRef("agent://planner"),
        operation_id=OpId("op1"),
        timestamp=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        evidence_refs=("wm://case/evidence#v1",),
    )

    assert provenance.to_json_obj() == {
        "source_refs": [
            "wm://case/input#v1",
            {"kind": "ref", "id": "%source"},
        ],
        "produced_by": "agent://planner",
        "operation_id": "op1",
        "timestamp": "2025-01-02T03:04:05+00:00",
        "evidence_refs": ["wm://case/evidence#v1"],
        "confidence": None,
    }
    assert Provenance.from_json_obj(provenance.to_json_obj()) == provenance
