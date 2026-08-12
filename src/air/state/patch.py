"""Validated immutable state patch proposals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from ..ir.ids import ActorRef, PatchId
from ..ir.provenance import Provenance
from ..ir.refs import StateRef, normalize_relative_path, normalize_write_scope
from ..ir.values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json
from .errors import InvalidPatchError


@dataclass(frozen=True, slots=True)
class Patch:
    """A proposed state update that is not applied until StateStore.commit."""

    patch_id: PatchId | str
    target: StateRef | str
    base_version: int | str
    writes: FrozenDict[str, JsonValue] | Mapping[str, JsonInput]
    declared_write_set: tuple[str, ...] = field(default_factory=tuple)
    produced_by: ActorRef | str | None = None
    provenance: Provenance = Provenance()

    def __post_init__(self) -> None:
        if not isinstance(self.patch_id, PatchId):
            object.__setattr__(self, "patch_id", PatchId(self.patch_id))
        if not isinstance(self.target, StateRef):
            object.__setattr__(self, "target", StateRef.parse(self.target))
        version = self.base_version
        if isinstance(version, str) and version.startswith("v"):
            version = version[1:]
        if isinstance(version, bool) or not isinstance(version, (int, str)):
            raise InvalidPatchError("base_version must be an integer or vN string")
        try:
            normalized_version = int(version)
        except (TypeError, ValueError) as exc:
            raise InvalidPatchError(f"invalid base_version: {self.base_version!r}") from exc
        if normalized_version < 1:
            raise InvalidPatchError("base_version must be positive")
        object.__setattr__(self, "base_version", normalized_version)
        frozen_writes = freeze_json(self.writes)
        if not isinstance(frozen_writes, FrozenDict) or not frozen_writes:
            raise InvalidPatchError("writes must be a non-empty JSON object")
        normalized_writes: dict[str, JsonValue] = {}
        for path, value in frozen_writes.items():
            if not isinstance(path, str):
                raise InvalidPatchError("patch write paths must be strings")
            normalized_path = normalize_relative_path(path)
            if normalized_path in normalized_writes:
                raise InvalidPatchError(f"duplicate normalized write path: {normalized_path!r}")
            normalized_writes[normalized_path] = value
        object.__setattr__(self, "writes", FrozenDict(normalized_writes))
        declared = tuple(normalize_write_scope(path) for path in self.declared_write_set)
        if not declared:
            raise InvalidPatchError("declared_write_set must not be empty")
        object.__setattr__(self, "declared_write_set", declared)
        if not isinstance(self.provenance, Provenance):
            raise InvalidPatchError("provenance must be a Provenance object")
        if self.produced_by is not None and not isinstance(self.produced_by, ActorRef):
            object.__setattr__(self, "produced_by", ActorRef(self.produced_by))

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(self.writes)

    @property
    def fingerprint(self) -> str:
        target = cast(StateRef, self.target)
        payload = {
            "base_version": self.base_version,
            "declared_write_set": self.declared_write_set,
            "produced_by": str(self.produced_by) if self.produced_by is not None else None,
            "provenance": self.provenance.to_json_obj(),
            "target": str(target),
            "writes": thaw_json(cast(FrozenDict[str, JsonValue], self.writes)),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
