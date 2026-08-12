"""Effects and capability rules for the canonical AIR model."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from .errors import AIRModelError, SerializationError
from .values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json


class EffectKind(StrEnum):
    READ = "read"
    WRITE = "write"
    SEND = "send"
    TOOL = "tool"
    EGRESS = "egress"
    MONEY = "money"
    HUMAN = "human"
    CUSTOM = "custom"

    @classmethod
    def from_json(cls, value: object) -> EffectKind:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise SerializationError("effect kind must be a string")
        try:
            return cls(value)
        except ValueError as exc:
            raise SerializationError(f"unknown effect kind: {value!r}") from exc


def _validate_resource(resource: str, label: str = "effect resource") -> str:
    if not isinstance(resource, str) or not resource or any(ord(char) < 32 for char in resource):
        raise AIRModelError(f"invalid {label}: {resource!r}")
    return resource


@dataclass(frozen=True, slots=True)
class Effect:
    """An operation effect, independent from the actor capability that permits it."""

    kind: EffectKind | str
    resource: str
    attributes: FrozenDict[str, JsonValue] | dict[str, JsonInput] = field(
        default_factory=FrozenDict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EffectKind.from_json(self.kind))
        object.__setattr__(self, "resource", _validate_resource(self.resource))
        frozen = freeze_json(self.attributes)
        if not isinstance(frozen, FrozenDict):
            raise AIRModelError("effect attributes must be a JSON object")
        object.__setattr__(self, "attributes", frozen)

    @classmethod
    def from_string(cls, value: str) -> Effect:
        if not isinstance(value, str) or ":" not in value:
            raise SerializationError(f"invalid effect spelling: {value!r}")
        kind, resource = value.split(":", 1)
        return cls(EffectKind.from_json(kind), resource)

    @classmethod
    def from_json_obj(cls, raw: object) -> Effect:
        if isinstance(raw, str):
            return cls.from_string(raw)
        if not isinstance(raw, dict):
            raise SerializationError("effect must be a string or object")
        unknown = set(raw) - {"kind", "resource", "attributes"}
        if unknown:
            raise SerializationError(f"unknown effect fields: {sorted(unknown)!r}")
        if "kind" not in raw or "resource" not in raw:
            raise SerializationError("effect requires kind and resource")
        attributes = raw.get("attributes", {})
        if not isinstance(attributes, dict):
            raise SerializationError("effect attributes must be an object")
        return cls(EffectKind.from_json(raw["kind"]), raw["resource"], attributes)

    def to_json_obj(self) -> dict[str, object]:
        attributes = cast(FrozenDict[str, JsonValue], self.attributes)
        kind = cast(EffectKind, self.kind)
        return {
            "attributes": thaw_json(attributes),
            "kind": kind.value,
            "resource": self.resource,
        }

    def __str__(self) -> str:
        return f"{cast(EffectKind, self.kind).value}:{self.resource}"


@dataclass(frozen=True, slots=True)
class CapabilityRule:
    """Allow or deny one effect kind/resource pattern."""

    kind: EffectKind | str
    resource_pattern: str
    allow: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EffectKind.from_json(self.kind))
        object.__setattr__(
            self,
            "resource_pattern",
            _validate_resource(self.resource_pattern, "capability pattern"),
        )
        if not isinstance(self.allow, bool):
            raise AIRModelError("capability rule allow flag must be boolean")

    @property
    def pattern(self) -> str:
        """Short alias for the resource pattern."""

        return self.resource_pattern

    def matches(self, effect: Effect) -> bool:
        return self.kind == effect.kind and _glob_match(effect.resource, self.resource_pattern)

    @classmethod
    def from_string(cls, value: str) -> CapabilityRule:
        if not isinstance(value, str) or not value:
            raise SerializationError(f"invalid capability spelling: {value!r}")
        allow = True
        raw = value
        if raw.startswith("allow ") or raw.startswith("deny "):
            verb, raw = raw.split(None, 1)
            allow = verb == "allow"
            parts = raw.split(None, 1)
            if len(parts) != 2:
                raise SerializationError(f"invalid capability spelling: {value!r}")
            kind, pattern = parts
        else:
            if raw.startswith("deny:"):
                allow = False
                raw = raw[5:]
            if ":" not in raw:
                raise SerializationError(f"invalid capability spelling: {value!r}")
            kind, pattern = raw.split(":", 1)
        return cls(EffectKind.from_json(kind), pattern, allow)

    def to_json_value(self) -> str:
        kind = cast(EffectKind, self.kind)
        if self.allow:
            return f"{kind.value}:{self.resource_pattern}"
        return f"deny:{kind.value}:{self.resource_pattern}"


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """Immutable ordered capability rules with deny-overrides-allow semantics."""

    rules: tuple[CapabilityRule, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized: list[CapabilityRule] = []
        for rule in self.rules:
            if isinstance(rule, CapabilityRule):
                normalized.append(rule)
            elif isinstance(rule, str):
                normalized.append(CapabilityRule.from_string(rule))
            else:
                raise AIRModelError(f"invalid capability rule: {rule!r}")
        object.__setattr__(self, "rules", tuple(normalized))

    @classmethod
    def from_strings(cls, values: Iterable[str]) -> CapabilitySet:
        return cls(tuple(CapabilityRule.from_string(value) for value in values))

    def allows(self, effect: Effect) -> bool:
        matching = [rule for rule in self.rules if rule.matches(effect)]
        if any(not rule.allow for rule in matching):
            return False
        return any(rule.allow for rule in matching)

    def to_json_values(self) -> list[str]:
        return [rule.to_json_value() for rule in self.rules]


def _glob_match(resource: str, pattern: str) -> bool:
    """Match exact resources and slash-aware ``*``/``**`` patterns.

    ``*`` matches within one slash-delimited segment, while ``**`` matches
    across segments.  A trailing ``/**`` also matches the directory itself,
    making ``wm://case/**`` cover both the namespace root and its descendants.
    """

    if pattern.endswith("/**"):
        base = pattern[:-3].rstrip("/")
        if resource == base:
            return True
    expression: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*" and index + 1 < len(pattern) and pattern[index + 1] == "*":
            expression.append(".*")
            index += 2
        elif char == "*":
            expression.append("[^/]*")
            index += 1
        elif char == "?":
            expression.append("[^/]")
            index += 1
        else:
            expression.append(re.escape(char))
            index += 1
    return re.fullmatch("".join(expression), resource) is not None
