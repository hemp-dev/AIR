"""Immutable literal values and JSON-compatible containers for AIR."""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from .errors import AIRModelError
from .ids import ValueRef
from .provenance import Provenance
from .types import TypeDescriptor, parse_type

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | tuple[JsonValue, ...] | FrozenDict[str, JsonValue]
type JsonInput = JsonScalar | list[JsonInput] | tuple[JsonInput, ...] | Mapping[str, JsonInput]


class FrozenDict[K, V](Mapping[K, V]):
    """Small hashable immutable mapping used inside semantic AST objects."""

    __slots__ = ("_data", "_hash")

    def __init__(
        self,
        values: Mapping[K, V] | tuple[tuple[K, V], ...] = (),
    ) -> None:
        copied = dict(values)
        self._data: Mapping[K, V] = copied
        self._hash: int | None = None

    def __getitem__(self, key: K) -> V:
        return self._data[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(sorted(self._data.items(), key=lambda item: repr(item[0]))))
        return self._hash

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._data)!r})"


def freeze_json(value: JsonInput | JsonValue) -> JsonValue:
    """Copy JSON-compatible input into recursively immutable containers."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AIRModelError("JSON numbers must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AIRModelError("JSON object keys must be strings")
            frozen[key] = freeze_json(item)
        return FrozenDict(frozen)
    raise AIRModelError(f"value is not JSON-compatible: {type(value).__name__}")


def thaw_json(value: JsonValue) -> object:
    """Convert an immutable JSON value back to ordinary JSON containers."""

    if isinstance(value, FrozenDict):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Literal:
    """A JSON-compatible literal with an optional explicit AIR type/provenance."""

    value: JsonValue | JsonInput
    type: TypeDescriptor | str | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))
        if isinstance(self.type, str):
            object.__setattr__(self, "type", parse_type(self.type))
        elif self.type is not None and not isinstance(self.type, TypeDescriptor):
            raise AIRModelError("literal type must be a TypeDescriptor or type spelling")


type Value = Literal | ValueRef
type ValueInput = Value | JsonInput


def as_value(value: ValueInput) -> Value:
    """Normalize a user-facing operand into a canonical literal or SSA reference."""

    if isinstance(value, (Literal, ValueRef)):
        return value
    return Literal(value)
