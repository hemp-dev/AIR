"""Deterministic immutable/versioned in-memory StateStore."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ..ir.provenance import Provenance, TrustLabel
from ..ir.refs import StateRef, normalize_relative_path
from ..ir.values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json
from .errors import (
    InvalidPatchError,
    PatchIntegrityError,
    StaleVersionError,
    StateNotFoundError,
    WriteScopeError,
)
from .objects import StateObject, StateProjection, as_object_mapping
from .patch import Patch


@dataclass(frozen=True, slots=True)
class CommitRecord:
    """Append-only state history record."""

    patch_id: str
    target: StateRef
    base_version: int
    committed_version: int
    changed_paths: tuple[str, ...]


class StateStore:
    """Small in-memory store exposing only immutable snapshots and commits."""

    def __init__(self) -> None:
        self._objects: dict[str, dict[int, StateObject]] = {}
        self._current: dict[str, int] = {}
        self._committed_patches: dict[str, tuple[str, StateObject]] = {}
        self._history: list[CommitRecord] = []

    def put(
        self,
        ref: StateRef | str,
        value: JsonInput,
        *,
        trust: TrustLabel = TrustLabel.SYSTEM_DERIVED,
        provenance: Provenance | None = None,
    ) -> StateObject:
        """Create a new named object version; intended for fixture initialization."""

        base = StateRef.parse(ref).base
        versions = self._objects.setdefault(base.uri, {})
        version = max(versions, default=0) + 1
        snapshot = StateObject(
            ref=base.with_object_id(f"v{version}"),
            version=version,
            value=freeze_json(value),
            trust=trust,
            provenance=provenance or Provenance(),
        )
        versions[version] = snapshot
        self._current[base.uri] = version
        return snapshot

    def read(self, ref: StateRef | str) -> StateObject:
        parsed = StateRef.parse(ref)
        versions = self._objects.get(parsed.base.uri)
        if versions is None:
            raise StateNotFoundError(f"state object not found: {parsed.base}")
        version = (
            _version_from_object_id(parsed.object_id)
            if parsed.object_id
            else self._current[parsed.base.uri]
        )
        try:
            return versions[version]
        except KeyError as exc:
            raise StateNotFoundError(f"state object not found: {parsed}") from exc

    def current_version(self, ref: StateRef | str) -> int:
        return self.read(StateRef.parse(ref).base).version

    def project(self, ref: StateRef | str, fields: Sequence[str]) -> StateProjection:
        snapshot = self.read(ref)
        normalized_fields = tuple(normalize_relative_path(field) for field in fields)
        if not normalized_fields:
            raise ValueError("projection fields must not be empty")
        result: dict[str, object] = {}
        for field in normalized_fields:
            value = _read_path(snapshot.value, field.split("."))
            _write_nested(result, field.split("."), thaw_json(value))
        return StateProjection(
            snapshot.ref,
            snapshot.version,
            normalized_fields,
            cast(JsonValue, freeze_json(cast(JsonInput, result))),
        )

    def commit(self, patch: Patch) -> StateObject:
        """Validate and atomically apply a patch, creating a new immutable version."""

        if not isinstance(patch, Patch):
            raise InvalidPatchError("commit requires a Patch")
        patch_key = str(patch.patch_id)
        previous = self._committed_patches.get(patch_key)
        if previous is not None:
            fingerprint, snapshot = previous
            if fingerprint == patch.fingerprint:
                return snapshot
            raise PatchIntegrityError(f"patch id replayed with different content: {patch_key}")
        target = cast(StateRef, patch.target)
        current = self.read(target.base)
        base_version = cast(int, patch.base_version)
        if current.version != base_version:
            raise StaleVersionError(str(target.base), base_version, current.version)
        for path in patch.changed_paths:
            if not any(
                _path_in_write_scope(path, declared) for declared in patch.declared_write_set
            ):
                raise WriteScopeError(
                    "patch path "
                    f"{path!r} is outside declared write set {patch.declared_write_set!r}"
                )
        updated = as_object_mapping(current.value)
        for path, value in cast(FrozenDict[str, JsonValue], patch.writes).items():
            _write_nested(updated, path.split("."), thaw_json(value))
        new_version = current.version + 1
        snapshot = StateObject(
            ref=current.base_ref.with_object_id(f"v{new_version}"),
            version=new_version,
            value=cast(JsonValue, freeze_json(cast(JsonInput, updated))),
            trust=current.trust,
            provenance=patch.provenance,
        )
        self._objects[current.base_ref.uri][new_version] = snapshot
        self._current[current.base_ref.uri] = new_version
        self._committed_patches[patch_key] = (patch.fingerprint, snapshot)
        self._history.append(
            CommitRecord(
                patch_id=patch_key,
                target=current.base_ref,
                base_version=current.version,
                committed_version=new_version,
                changed_paths=patch.changed_paths,
            )
        )
        return snapshot

    @property
    def history(self) -> tuple[CommitRecord, ...]:
        return tuple(self._history)


def _version_from_object_id(object_id: str | None) -> int:
    if object_id is None or not object_id.startswith("v"):
        raise StateNotFoundError(f"invalid state object version: {object_id!r}")
    try:
        version = int(object_id[1:])
    except ValueError as exc:
        raise StateNotFoundError(f"invalid state object version: {object_id!r}") from exc
    if version < 1:
        raise StateNotFoundError(f"invalid state object version: {object_id!r}")
    return version


def _read_path(value: JsonValue, path: Sequence[str]) -> JsonValue:
    current: object = value
    for segment in path:
        if not isinstance(current, (FrozenDict, dict)) or segment not in current:
            raise StateNotFoundError(f"state field not found: {'.'.join(path)}")
        current = current[segment]
    return cast(JsonValue, current)


def _write_nested(target: dict[str, object], path: Sequence[str], value: object) -> None:
    if not path:
        raise InvalidPatchError("state path must not be empty")
    current = target
    for segment in path[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[path[-1]] = value


def _path_in_write_scope(path: str, declared: str) -> bool:
    if path == declared:
        return True
    return declared.endswith(".*") and path.startswith(declared[:-2] + ".")
