from dataclasses import FrozenInstanceError

import pytest

from air.ir import ActorRef, InvalidIdentifierError, OpId, ProgramId, ResultId, ValueRef


@pytest.mark.parametrize(
    ("factory", "raw"),
    [
        (ProgramId, ""),
        (ProgramId, "program with spaces"),
        (OpId, "op/1"),
        (ResultId, "%"),
        (ActorRef, "planner"),
        (ActorRef, "agent://planner name"),
    ],
)
def test_invalid_identifiers_are_rejected(factory: object, raw: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        factory(raw)  # type: ignore[operator]


def test_result_ids_normalize_the_air_text_sigil() -> None:
    assert ResultId("1") == ResultId("%1")
    assert str(ResultId("1")) == "%1"
    assert ResultId("%1").bare == "1"
    assert ValueRef("1").id == ResultId("%1")


def test_ids_are_immutable() -> None:
    identifier = ProgramId("prog.demo")
    with pytest.raises(FrozenInstanceError):
        identifier.value = "prog.other"  # type: ignore[misc]
