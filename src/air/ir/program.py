"""Canonical AIR program/module container."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from .effects import CapabilitySet
from .errors import AIRModelError, DuplicateIdError
from .ids import ActorRef, OpId, ProgramId, ResultId
from .operations import Operation, ResultDecl
from .values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json

AIR_VERSION = "0.1"


@dataclass(frozen=True, slots=True)
class Program:
    """Immutable canonical AIR program.

    The constructor checks operation and SSA result uniqueness immediately so
    malformed programs cannot be mistaken for executable canonical IR.
    """

    program_id: ProgramId | str
    actor: ActorRef | str
    operations: tuple[Operation, ...] = field(default_factory=tuple)
    air_version: str = AIR_VERSION
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    metadata: FrozenDict[str, JsonValue] | Mapping[str, JsonInput] = field(
        default_factory=FrozenDict
    )

    def __post_init__(self) -> None:
        if not isinstance(self.program_id, ProgramId):
            object.__setattr__(self, "program_id", ProgramId(self.program_id))
        if not isinstance(self.actor, ActorRef):
            object.__setattr__(self, "actor", ActorRef(self.actor))
        if self.air_version != AIR_VERSION:
            raise AIRModelError(f"unsupported AIR version: {self.air_version!r}")
        operations = tuple(self.operations)
        if not all(isinstance(operation, Operation) for operation in operations):
            raise AIRModelError("program operations must be Operation objects")
        seen_operations: set[OpId] = set()
        seen_results: set[ResultId] = set()
        for operation in operations:
            operation_id = cast(OpId, operation.op_id)
            if operation_id in seen_operations:
                raise DuplicateIdError(f"duplicate operation id: {operation_id}")
            seen_operations.add(operation_id)
            for result in operation.results:
                result_id = cast(ResultId, result.id)
                if result_id in seen_results:
                    raise DuplicateIdError(f"duplicate SSA result id: {result_id}")
                seen_results.add(result_id)
        object.__setattr__(self, "operations", operations)
        if not isinstance(self.capabilities, CapabilitySet):
            object.__setattr__(self, "capabilities", CapabilitySet(tuple(self.capabilities)))
        frozen_metadata = freeze_json(self.metadata)
        if not isinstance(frozen_metadata, FrozenDict):
            raise AIRModelError("program metadata must be a JSON object")
        object.__setattr__(self, "metadata", frozen_metadata)

    @property
    def result_declarations(self) -> tuple[ResultDecl, ...]:
        """Return all result declarations in program order."""

        return tuple(result for operation in self.operations for result in operation.results)

    def json_metadata(self) -> dict[str, object]:
        """Return ordinary JSON containers for metadata inspection."""

        metadata = cast(FrozenDict[str, JsonValue], self.metadata)
        return cast(dict[str, object], thaw_json(metadata))

    def to_json(self) -> str:
        """Serialize this program using canonical AIR-JSON."""

        from .serde import serialize_program

        return serialize_program(self)

    @classmethod
    def from_json(cls, payload: str | bytes | Mapping[str, object]) -> Program:
        """Deserialize canonical AIR-JSON into a validated program."""

        from .serde import deserialize_program

        return deserialize_program(payload)
