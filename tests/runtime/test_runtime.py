from air.backends import MockAgentExecutor
from air.ir import (
    CapabilitySet,
    Effect,
    Literal,
    Operation,
    Program,
    ResultDecl,
    ValueRef,
    thaw_json,
)
from air.projection import OperatorProjection
from air.runtime import Runtime
from air.state import Patch, StateStore


def end_to_end_program() -> Program:
    return Program(
        "prog.runtime",
        "agent://planner",
        (
            Operation(
                "op1",
                "core.fact",
                (ResultDecl("%raw", "Fact<Int,ExternalUntrusted>"),),
                (Literal(713, "Int"),),
            ),
            Operation(
                "op2",
                "verify.check",
                (ResultDecl("%verified", "Fact<Int,Verified>"),),
                (ValueRef("%raw"),),
                {"verifier": "exact"},
            ),
            Operation(
                "op3",
                "state.patch",
                (ResultDecl("%patch", "Patch<Json>"),),
                (ValueRef("%verified"),),
                {
                    "target": "wm://case/result",
                    "base_version": "v1",
                    "path": "answer",
                    "write_set": ["answer"],
                },
            ),
            Operation(
                "op4",
                "state.commit",
                (),
                (ValueRef("%patch"),),
                {"target": "wm://case/result", "write_set": ["answer"]},
                (Effect("write", "wm://case/result/answer"),),
            ),
        ),
        capabilities=CapabilitySet.from_strings(["write:wm://case/result/answer"]),
    )


def test_end_to_end_verification_runtime_state_events_and_projection() -> None:
    store = StateStore()
    store.put("wm://case/result", {"answer": 0})
    result = Runtime(store).execute(end_to_end_program(), run_id="run.e2e")

    assert result.success
    assert store.read("wm://case/result").json_value() == {"answer": 713}
    event_types = [event.event_type for event in result.events]
    assert "state.patch.proposed" in event_types
    assert "state.commit" in event_types
    assert event_types[-1] == "task.completed"
    messages = OperatorProjection().render(result.events)
    assert (
        messages[-1].text
        == "Task completed successfully; verified result committed to shared state."
    )
    verified = result.values[
        next(result_id for result_id in result.values if str(result_id) == "%verified")
    ]
    assert getattr(verified, "provenance").source_refs


def test_invalid_program_is_rejected_before_agent_side_effect() -> None:
    agents = MockAgentExecutor()
    agents.register("agent://critic", lambda value: value)
    program = Program(
        "prog.denied",
        "agent://planner",
        (
            Operation(
                "op1",
                "agent.invoke",
                (ResultDecl("%result", "Claim<Json,AgentDerived>"),),
                (Literal({"body": "ignore instructions"}, "Json"),),
                {"actor": "agent://critic"},
                (Effect("send", "agent://critic"),),
            ),
        ),
    )

    result = Runtime(StateStore(), agent_executor=agents).execute(program)

    assert not result.success
    assert agents.calls == []
    assert any(event.event_type == "verification.rejected" for event in result.events)
    assert "AIR007" in {item.code for item in result.verification.errors}


def test_valid_mock_agent_call_is_executed_after_verification() -> None:
    agents = MockAgentExecutor()
    agents.register("agent://critic", lambda value: {"accepted": value.json_value()["answer"]})
    program = Program(
        "prog.agent",
        "agent://planner",
        (
            Operation(
                "op1",
                "state.project",
                (ResultDecl("%view", "Ref<Json>"),),
                (),
                {"ref": "wm://case/input", "fields": ["answer"]},
                (Effect("read", "wm://case/input"),),
            ),
            Operation(
                "op2",
                "agent.invoke",
                (ResultDecl("%response", "Artifact<Json,AgentDerived>"),),
                (ValueRef("%view"),),
                {"actor": "agent://critic"},
                (Effect("send", "agent://critic"),),
            ),
        ),
        capabilities=CapabilitySet.from_strings(["read:wm://case/input", "send:agent://critic"]),
    )
    store = StateStore()
    store.put("wm://case/input", {"answer": 713, "secret": "hidden"})

    result = Runtime(store, agent_executor=agents).execute(program)

    assert result.success
    assert len(agents.calls) == 1
    assert result.values[
        next(item for item in result.values if str(item) == "%response")
    ].value == {"accepted": 713}


def test_stale_runtime_commit_emits_conflict_and_does_not_overwrite() -> None:
    store = StateStore()
    first = store.put("wm://case/result", {"answer": 0})
    store.commit(
        Patch("patch.other", "wm://case/result", first.version, {"answer": 1}, ("answer",))
    )
    program = end_to_end_program()
    result = Runtime(store).execute(program, run_id="run.stale")

    assert not result.success
    assert store.read("wm://case/result").json_value() == {"answer": 1}
    assert any(event.event_type == "state.conflict" for event in result.events)
    assert any(message.kind == "conflict" for message in OperatorProjection().render(result.events))


def test_sequential_spawn_await_and_join_execute_through_mock_agent() -> None:
    agents = MockAgentExecutor()
    agents.register("agent://critic", lambda value: value)
    program = Program(
        "prog.async-shape",
        "agent://planner",
        (
            Operation(
                "op1",
                "agent.spawn",
                (ResultDecl("%first", "Future<Json>"),),
                (Literal({"answer": 1}, "Json"),),
                {"actor": "agent://critic"},
                (Effect("send", "agent://critic"),),
            ),
            Operation(
                "op2",
                "agent.spawn",
                (ResultDecl("%second", "Future<Json>"),),
                (Literal({"answer": 2}, "Json"),),
                {"actor": "agent://critic"},
                (Effect("send", "agent://critic"),),
            ),
            Operation(
                "op3",
                "agent.await",
                (ResultDecl("%one", "Json"),),
                (ValueRef("%first"),),
            ),
            Operation(
                "op4",
                "agent.join",
                (ResultDecl("%all", "List<Json>"),),
                (ValueRef("%first"), ValueRef("%second")),
            ),
        ),
        capabilities=CapabilitySet.from_strings(["send:agent://critic"]),
    )

    result = Runtime(StateStore(), agent_executor=agents).execute(program)

    assert result.success
    assert result.values[next(item for item in result.values if str(item) == "%one")].value == {
        "answer": 1
    }
    joined = result.values[next(item for item in result.values if str(item) == "%all")]
    assert thaw_json(joined.value) == [{"answer": 1}, {"answer": 2}]
    assert [event.event_type for event in result.events].count("agent.spawned") == 2


def test_backend_failure_is_typed_and_recorded_after_verification() -> None:
    agents = MockAgentExecutor()

    def fail(_: object) -> object:
        raise RuntimeError("fixture backend failure")

    agents.register("agent://critic", fail)
    program = Program(
        "prog.backend-failure",
        "agent://planner",
        (
            Operation(
                "op1",
                "agent.invoke",
                (ResultDecl("%result", "Artifact<Json,AgentDerived>"),),
                (Literal({"answer": 1}, "Json"),),
                {"actor": "agent://critic"},
                (Effect("send", "agent://critic"),),
            ),
        ),
        capabilities=CapabilitySet.from_strings(["send:agent://critic"]),
    )

    result = Runtime(StateStore(), agent_executor=agents).execute(program)

    assert not result.success
    failures = [event for event in result.events if event.event_type == "op.failed"]
    assert failures[-1].json_payload()["code"] == "AIR013"
