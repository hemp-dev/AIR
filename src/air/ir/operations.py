"""Immutable operation and result declaration objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from .effects import Effect
from .errors import AIRModelError, DuplicateIdError
from .ids import OpId, ResultId
from .types import TypeDescriptor
from .values import (
    FrozenDict,
    JsonInput,
    JsonValue,
    Value,
    as_value,
    freeze_json,
    thaw_json,
)

_OPCODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Optional source position retained for future parser diagnostics."""

    line: int
    column: int
    source: str | None = None

    def __post_init__(self) -> None:
        if self.line < 1 or self.column < 1:
            raise AIRModelError("source location line and column are one-based")


@dataclass(frozen=True, slots=True)
class ResultDecl:
    """One SSA result and its declared canonical type."""

    id: ResultId | str
    type: TypeDescriptor | str

    def __post_init__(self) -> None:
        if not isinstance(self.id, ResultId):
            object.__setattr__(self, "id", ResultId(self.id))
        if isinstance(self.type, str):
            object.__setattr__(self, "type", TypeDescriptor.from_text(self.type))
        elif not isinstance(self.type, TypeDescriptor):
            raise AIRModelError("result type must be a TypeDescriptor or type spelling")


@dataclass(frozen=True, slots=True)
class Operation:
    """Canonical operation node; it has no execution behavior."""

    op_id: OpId | str
    opcode: str
    results: tuple[ResultDecl, ...] = field(default_factory=tuple)
    operands: tuple[Value, ...] = field(default_factory=tuple)
    attributes: FrozenDict[str, JsonValue] | Mapping[str, JsonInput] = field(
        default_factory=FrozenDict
    )
    declared_effects: tuple[Effect, ...] = field(default_factory=tuple)
    source_location: SourceLocation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.op_id, OpId):
            object.__setattr__(self, "op_id", OpId(self.op_id))
        if not isinstance(self.opcode, str) or _OPCODE_RE.fullmatch(self.opcode) is None:
            raise AIRModelError(f"invalid opcode: {self.opcode!r}")
        normalized_results = tuple(
            result if isinstance(result, ResultDecl) else ResultDecl(result["id"], result["type"])
            for result in self.results
        )
        result_ids = [result.id for result in normalized_results]
        if len(set(result_ids)) != len(result_ids):
            raise DuplicateIdError(f"duplicate result id in operation {self.op_id}")
        object.__setattr__(self, "results", normalized_results)
        object.__setattr__(self, "operands", tuple(as_value(operand) for operand in self.operands))
        frozen_attributes = freeze_json(self.attributes)
        if not isinstance(frozen_attributes, FrozenDict):
            raise AIRModelError("operation attributes must be a JSON object")
        object.__setattr__(self, "attributes", frozen_attributes)
        normalized_effects = tuple(
            effect if isinstance(effect, Effect) else Effect.from_json_obj(effect)
            for effect in self.declared_effects
        )
        object.__setattr__(self, "declared_effects", normalized_effects)

    def attribute(self, name: str, default: JsonValue | None = None) -> JsonValue | None:
        """Read one immutable JSON attribute."""

        attributes = cast(FrozenDict[str, JsonValue], self.attributes)
        return attributes.get(name, default)

    def json_attributes(self) -> dict[str, object]:
        """Return ordinary JSON containers for inspection/serialization."""

        attributes = cast(FrozenDict[str, JsonValue], self.attributes)
        return cast(dict[str, object], thaw_json(attributes))
