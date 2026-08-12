import json
from datetime import UTC, datetime

import pytest

from air.ir import (
    INT,
    ActorRef,
    CapabilitySet,
    Effect,
    Literal,
    Operation,
    OpId,
    Program,
    Provenance,
    ResultDecl,
    SerializationError,
    SourceLocation,
    Task,
    ValueRef,
    deserialize_program,
    serialize_program,
    serialize_program_bytes,
)


def build_program() -> Program:
    provenance = Provenance(
        source_refs=("wm://case/input#v1", ValueRef("%source")),
        produced_by=ActorRef("agent://planner"),
        operation_id=OpId("op1"),
        timestamp=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        evidence_refs=("wm://case/evidence#v1",),
    )
    fact = Operation(
        op_id="op1",
        opcode="core.fact",
        results=(ResultDecl("%fact", INT),),
        operands=(Literal(713, INT, provenance),),
        attributes={"kind": "secret", "labels": ["relay", "deterministic"]},
        source_location=SourceLocation(3, 5, "fixture.air"),
    )
    read = Operation(
        op_id="op2",
        opcode="state.read",
        results=(ResultDecl("%input", "Ref<Json>"),),
        operands=(ValueRef("%fact"),),
        declared_effects=(Effect("read", "wm://case/input"),),
    )
    return Program(
        program_id="prog.roundtrip",
        actor="agent://planner",
        operations=(fact, read),
        capabilities=CapabilitySet.from_strings(
            ["read:wm://case/**", "deny:write:wm://case/private/**"]
        ),
        metadata={"seed": 7, "fixture": {"name": "relay", "enabled": True}},
        task=Task("task.relay", Literal("relay", "String"), {"seed": 7}),
    )


def test_program_json_round_trip_and_deterministic_bytes() -> None:
    program = build_program()
    encoded = serialize_program(program)
    restored = deserialize_program(encoded)

    assert restored == program
    assert serialize_program(restored) == encoded
    assert serialize_program_bytes(program) == encoded.encode("utf-8")
    assert list(json.loads(encoded)) == sorted(json.loads(encoded))


def test_task_metadata_and_goal_survive_round_trip() -> None:
    program = build_program()
    restored = deserialize_program(serialize_program(program))

    assert restored.task == program.task
    assert restored.task is not None
    assert restored.task.json_metadata() == {"seed": 7}


def test_malformed_json_and_duplicate_keys_are_rejected() -> None:
    with pytest.raises(SerializationError):
        deserialize_program('{"air_version":"0.1","air_version":"0.1"}')
    with pytest.raises(SerializationError):
        deserialize_program('{"air_version":"0.1"}')


def test_unknown_fields_and_effects_are_rejected() -> None:
    payload = json.loads(serialize_program(build_program()))
    payload["unexpected"] = True
    with pytest.raises(SerializationError, match="unknown program fields"):
        deserialize_program(payload)

    payload = json.loads(serialize_program(build_program()))
    payload["operations"][1]["declared_effects"][0]["kind"] = "launch"
    with pytest.raises(SerializationError, match="unknown effect kind"):
        deserialize_program(payload)
