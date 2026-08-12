"""Immutable state snapshots and projected views."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from ..ir.provenance import Provenance, TrustLabel
from ..ir.refs import StateRef
from ..ir.values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json


@dataclass(frozen=True, slots=True)
class StateObject:
    """One immutable version of a named state object."""

    ref: StateRef
    version: int
    value: JsonValue
    trust: TrustLabel = TrustLabel.SYSTEM_DERIVED
    provenance: Provenance = Provenance()

    def __post_init__(self) -> None:
        if not isinstance(self.ref, StateRef):
            raise ValueError("state object ref must be a StateRef")
        if self.ref.object_id is None:
            raise ValueError("state object ref must include an object id")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("state object versions start at one")
        object.__setattr__(self, "value", freeze_json(self.value))
        if not isinstance(self.trust, TrustLabel):
            object.__setattr__(self, "trust", TrustLabel.from_json(self.trust))
        if not isinstance(self.provenance, Provenance):
            raise ValueError("state object provenance must be a Provenance object")

    @property
    def base_ref(self) -> StateRef:
        return self.ref.base

    def json_value(self) -> object:
        return thaw_json(self.value)


@dataclass(frozen=True, slots=True)
class StateProjection:
    """A minimal materialized view of selected state paths."""

    source_ref: StateRef
    version: int
    fields: tuple[str, ...]
    value: JsonValue

    def __post_init__(self) -> None:
        if not isinstance(self.source_ref, StateRef):
            raise ValueError("projection source_ref must be a StateRef")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("projection versions start at one")
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "value", freeze_json(self.value))

    @property
    def materialized_bytes(self) -> int:
        encoded = json.dumps(
            thaw_json(self.value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return len(encoded.encode("utf-8"))

    def json_value(self) -> object:
        return thaw_json(self.value)


def as_object_mapping(value: JsonValue | JsonInput) -> dict[str, object]:
    """Return a mutable top-level copy for a patch operation."""

    frozen = freeze_json(value)
    if not isinstance(frozen, FrozenDict):
        raise TypeError("state patch targets must contain a JSON object")
    return cast(dict[str, object], thaw_json(frozen))
