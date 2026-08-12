from air.ir import (
    BOOL,
    CapabilitySet,
    Effect,
    Literal,
    Operation,
    Program,
    ResultDecl,
    ValueRef,
)
from air.verifier import Verifier


def report_for(*operations: Operation, capabilities: tuple[str, ...] = ()):
    return Verifier().verify(
        Program(
            "prog.verify",
            "agent://planner",
            operations,
            capabilities=CapabilitySet.from_strings(capabilities),
        )
    )


def codes(report: object) -> set[str]:
    return {diagnostic.code for diagnostic in report.diagnostics}  # type: ignore[union-attr]


def test_unknown_opcode_is_rejected() -> None:
    report = report_for(Operation("op1", "unknown.dialect", ()))
    assert "AIR002" in codes(report)


def test_undefined_reference_and_wrong_type_are_rejected() -> None:
    report = report_for(
        Operation("op1", "verify.assert", (), (Literal(1, "Int"),)),
        Operation("op2", "verify.assert", (), (ValueRef("%missing"),)),
    )
    assert {"AIR004", "AIR005"}.issubset(codes(report))


def test_invalid_state_reference_and_scope_are_rejected() -> None:
    report = report_for(
        Operation(
            "op1",
            "state.patch",
            (ResultDecl("%patch", "Patch<Json>"),),
            (Literal(1, "Int"),),
            {
                "target": "wm://case/../payments",
                "base_version": "v1",
                "path": "payments.account",
                "write_set": ["case.result"],
            },
        )
    )
    assert {"AIR009", "AIR010"}.issubset(codes(report))


def test_unknown_effect_and_unauthorized_effect_fail_closed() -> None:
    unknown = report_for(
        Operation(
            "op1",
            "human.notify",
            (),
            declared_effects=(Effect("custom", "mystery"),),
        )
    )
    denied = report_for(
        Operation(
            "op2",
            "human.notify",
            (),
            declared_effects=(Effect("human", "notify"),),
        )
    )
    assert "AIR006" in codes(unknown)
    assert "AIR007" in codes(denied)


def test_untrusted_to_verified_requires_verify_check() -> None:
    direct = report_for(
        Operation(
            "op1",
            "core.fact",
            (ResultDecl("%fact", "Fact<Int,Verified>"),),
            (Literal(7, "Int"),),
        )
    )
    valid = report_for(
        Operation(
            "op1",
            "core.fact",
            (ResultDecl("%fact", "Fact<Int,ExternalUntrusted>"),),
            (Literal(7, "Int"),),
        ),
        Operation(
            "op2",
            "verify.check",
            (ResultDecl("%verified", "Fact<Int,Verified>"),),
            (ValueRef("%fact"),),
            {"verifier": "exact"},
        ),
    )
    assert "AIR008" in codes(direct)
    assert valid.ok


def test_capability_and_effect_declaration_are_checked_for_state_commit() -> None:
    operation = Operation(
        "op1",
        "state.commit",
        (),
        (ValueRef("%patch"),),
        {"target": "wm://case/result", "write_set": ["answer"]},
        (Effect("write", "wm://case/result/answer"),),
    )
    report = report_for(operation)
    assert {"AIR004", "AIR005", "AIR007"}.issubset(codes(report))


def test_valid_assertion_program_is_accepted() -> None:
    report = report_for(Operation("op1", "verify.assert", (), (Literal(True, BOOL),)))
    assert report.ok


def test_spawn_await_and_join_have_checked_future_shapes() -> None:
    report = report_for(
        Operation(
            "op1",
            "agent.spawn",
            (ResultDecl("%first", "Future<Artifact<Json,AgentDerived>>"),),
            (Literal({"answer": 1}, "Json"),),
            {"actor": "agent://critic"},
            (Effect("send", "agent://critic"),),
        ),
        Operation(
            "op2",
            "agent.spawn",
            (ResultDecl("%second", "Future<Artifact<Json,AgentDerived>>"),),
            (Literal({"answer": 2}, "Json"),),
            {"actor": "agent://critic"},
            (Effect("send", "agent://critic"),),
        ),
        Operation(
            "op3",
            "agent.await",
            (ResultDecl("%answer", "Artifact<Json,AgentDerived>"),),
            (ValueRef("%first"),),
        ),
        Operation(
            "op4",
            "agent.join",
            (ResultDecl("%answers", "List<Artifact<Json,AgentDerived>>"),),
            (ValueRef("%first"), ValueRef("%second")),
        ),
        capabilities=("send:agent://critic",),
    )
    assert report.ok


def test_read_projection_cannot_escape_declared_field_scope() -> None:
    report = report_for(
        Operation(
            "op1",
            "state.project",
            (ResultDecl("%view", "Ref<Json>"),),
            (),
            {
                "ref": "wm://case/input",
                "fields": ["secret"],
                "read_set": ["public"],
            },
            (Effect("read", "wm://case/input"),),
        ),
        capabilities=("read:wm://case/input",),
    )
    assert "AIR007" in codes(report)


def test_risky_effect_requires_explicit_human_authorization_context() -> None:
    operation = Operation(
        "op1",
        "human.notify",
        (),
        declared_effects=(Effect("money", "EUR<=800"),),
    )
    denied = report_for(operation, capabilities=("money:EUR<=800",))
    assert "AIR014" in codes(denied)
