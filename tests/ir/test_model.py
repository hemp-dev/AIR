import pytest

from air.ir import (
    INT,
    DuplicateIdError,
    Effect,
    Literal,
    Operation,
    OpId,
    Program,
    ResultDecl,
    ResultId,
    ValueRef,
)


def test_operation_normalizes_literals_and_refs() -> None:
    operation = Operation(
        op_id=OpId("op1"),
        opcode="core.fact",
        results=(ResultDecl(ResultId("%fact"), INT),),
        operands=(Literal(713, INT), ValueRef("%other")),
        declared_effects=(Effect("read", "wm://case/input"),),
    )

    assert operation.results[0].id == ResultId("%fact")
    assert operation.operands == (Literal(713, INT), ValueRef("%other"))
    assert operation.declared_effects[0].resource == "wm://case/input"


def test_duplicate_result_ids_are_rejected_at_program_boundary() -> None:
    first = Operation("op1", "core.fact", (ResultDecl("%same", INT),))
    second = Operation("op2", "core.fact", (ResultDecl(ResultId("same"), INT),))

    with pytest.raises(DuplicateIdError, match="duplicate SSA result id"):
        Program("prog.duplicate", "agent://planner", (first, second))


def test_duplicate_operation_ids_are_rejected() -> None:
    first = Operation("op1", "core.fact")
    second = Operation("op1", "core.claim")

    with pytest.raises(DuplicateIdError, match="duplicate operation id"):
        Program("prog.duplicate", "agent://planner", (first, second))
