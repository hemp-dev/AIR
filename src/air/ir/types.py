"""Small immutable type descriptors for canonical AIR values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

from .errors import AIRModelError, SerializationError
from .provenance import TrustLabel


class PrimitiveKind(StrEnum):
    BOOL = "Bool"
    INT = "Int"
    FLOAT = "Float"
    STRING = "String"
    BYTES = "Bytes"
    TIMESTAMP = "Timestamp"
    JSON = "Json"


class SemanticKind(StrEnum):
    FACT = "Fact"
    CLAIM = "Claim"
    HYPOTHESIS = "Hypothesis"
    GOAL = "Goal"
    CONSTRAINT = "Constraint"
    DECISION = "Decision"
    ARTIFACT = "Artifact"


class RuntimeKind(StrEnum):
    REF = "Ref"
    FUTURE = "Future"
    PATCH = "Patch"
    RESULT = "Result"
    SNAPSHOT = "Snapshot"


class TypeDescriptor:
    """Base class for canonical AIR type descriptors."""

    def __str__(self) -> str:
        return self.to_text()

    def to_text(self) -> str:
        raise NotImplementedError

    @classmethod
    def from_text(cls, text: str) -> TypeDescriptor:
        return parse_type(text)

    @classmethod
    def from_json(cls, value: object) -> TypeDescriptor:
        if not isinstance(value, str):
            raise SerializationError("type descriptor must be a string")
        return parse_type(value)


@dataclass(frozen=True, slots=True)
class PrimitiveType(TypeDescriptor):
    kind: PrimitiveKind | str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PrimitiveKind):
            try:
                object.__setattr__(self, "kind", PrimitiveKind(self.kind))
            except ValueError as exc:
                raise AIRModelError(f"unknown primitive type: {self.kind!r}") from exc

    def to_text(self) -> str:
        return cast(PrimitiveKind, self.kind).value


@dataclass(frozen=True, slots=True)
class ListType(TypeDescriptor):
    element: TypeDescriptor

    def to_text(self) -> str:
        return f"List<{self.element}>"


@dataclass(frozen=True, slots=True)
class MapType(TypeDescriptor):
    key: TypeDescriptor
    value: TypeDescriptor

    def to_text(self) -> str:
        return f"Map<{self.key},{self.value}>"


@dataclass(frozen=True, slots=True)
class OptionalType(TypeDescriptor):
    value: TypeDescriptor

    def to_text(self) -> str:
        return f"Optional<{self.value}>"


@dataclass(frozen=True, slots=True)
class TupleType(TypeDescriptor):
    elements: tuple[TypeDescriptor, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "elements", tuple(self.elements))

    def to_text(self) -> str:
        return f"Tuple<{','.join(str(element) for element in self.elements)}>"


@dataclass(frozen=True, slots=True)
class SemanticType(TypeDescriptor):
    kind: SemanticKind | str
    value: TypeDescriptor
    trust: TrustLabel | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SemanticKind):
            try:
                object.__setattr__(self, "kind", SemanticKind(self.kind))
            except ValueError as exc:
                raise AIRModelError(f"unknown semantic type: {self.kind!r}") from exc
        if not isinstance(self.value, TypeDescriptor):
            raise AIRModelError("semantic type value must be a TypeDescriptor")
        if self.kind in {SemanticKind.GOAL, SemanticKind.CONSTRAINT}:
            if self.trust is not None:
                kind = cast(SemanticKind, self.kind)
                raise AIRModelError(f"{kind.value} does not carry a trust label")
        else:
            if self.trust is None:
                kind = cast(SemanticKind, self.kind)
                raise AIRModelError(f"{kind.value} requires a trust label")
            if not isinstance(self.trust, TrustLabel):
                object.__setattr__(self, "trust", TrustLabel.from_json(self.trust))

    def to_text(self) -> str:
        kind = cast(SemanticKind, self.kind)
        if self.trust is None:
            return f"{kind.value}<{self.value}>"
        trust = cast(TrustLabel, self.trust)
        return f"{kind.value}<{self.value},{trust.value}>"


@dataclass(frozen=True, slots=True)
class RuntimeType(TypeDescriptor):
    kind: RuntimeKind | str
    value: TypeDescriptor
    error: TypeDescriptor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimeKind):
            try:
                object.__setattr__(self, "kind", RuntimeKind(self.kind))
            except ValueError as exc:
                raise AIRModelError(f"unknown runtime type: {self.kind!r}") from exc
        if not isinstance(self.value, TypeDescriptor):
            raise AIRModelError("runtime type value must be a TypeDescriptor")
        if self.kind == RuntimeKind.RESULT:
            if self.error is None or not isinstance(self.error, TypeDescriptor):
                raise AIRModelError("Result<T,E> requires an error type")
        elif self.error is not None:
            kind = cast(RuntimeKind, self.kind)
            raise AIRModelError(f"{kind.value} accepts one type parameter")

    def to_text(self) -> str:
        kind = cast(RuntimeKind, self.kind)
        if self.kind == RuntimeKind.RESULT:
            return f"Result<{self.value},{self.error}>"
        return f"{kind.value}<{self.value}>"


BOOL: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.BOOL)
INT: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.INT)
FLOAT: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.FLOAT)
STRING: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.STRING)
BYTES: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.BYTES)
TIMESTAMP: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.TIMESTAMP)
JSON: Final[PrimitiveType] = PrimitiveType(PrimitiveKind.JSON)


def _parse_name(text: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(text) and (text[index].isalnum() or text[index] in "_.-"):
        index += 1
    if start == index:
        raise SerializationError(f"expected type name at offset {index}")
    return text[start:index], index


class _TypeParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0

    def parse(self) -> TypeDescriptor:
        result = self._parse_type_or_trust(allow_trust=False)
        if self.index != len(self.text):
            raise SerializationError(f"unexpected type text at offset {self.index}")
        if not isinstance(result, TypeDescriptor):
            raise SerializationError("trust label cannot be a top-level type")
        return result

    def _parse_type_or_trust(self, *, allow_trust: bool) -> TypeDescriptor | TrustLabel:
        name, self.index = _parse_name(self.text, self.index)
        if self.index < len(self.text) and self.text[self.index] == "<":
            self.index += 1
            arguments: list[TypeDescriptor | TrustLabel] = []
            if self.index < len(self.text) and self.text[self.index] == ">":
                self.index += 1
            else:
                while True:
                    arguments.append(self._parse_type_or_trust(allow_trust=True))
                    if self.index >= len(self.text):
                        raise SerializationError("unterminated generic type")
                    if self.text[self.index] == ">":
                        self.index += 1
                        break
                    if self.text[self.index] != ",":
                        raise SerializationError(f"expected ',' or '>' at offset {self.index}")
                    self.index += 1
            return self._build_generic(name, arguments)

        try:
            return PrimitiveType(PrimitiveKind(name))
        except ValueError:
            pass
        if allow_trust:
            try:
                return TrustLabel(name)
            except ValueError:
                pass
        raise SerializationError(f"unknown type name: {name!r}")

    def _build_generic(
        self,
        name: str,
        arguments: list[TypeDescriptor | TrustLabel],
    ) -> TypeDescriptor:
        def one_type() -> TypeDescriptor:
            if len(arguments) != 1 or not isinstance(arguments[0], TypeDescriptor):
                raise SerializationError(f"{name} expects one type argument")
            return arguments[0]

        if name == "List":
            return ListType(one_type())
        if name == "Optional":
            return OptionalType(one_type())
        if name == "Ref":
            return RuntimeType(RuntimeKind.REF, one_type())
        if name == "Future":
            return RuntimeType(RuntimeKind.FUTURE, one_type())
        if name == "Patch":
            return RuntimeType(RuntimeKind.PATCH, one_type())
        if name == "Snapshot":
            return RuntimeType(RuntimeKind.SNAPSHOT, one_type())
        if name == "Map":
            if len(arguments) != 2 or not all(
                isinstance(argument, TypeDescriptor) for argument in arguments
            ):
                raise SerializationError("Map expects two type arguments")
            typed_arguments = cast(tuple[TypeDescriptor, TypeDescriptor], tuple(arguments))
            return MapType(*typed_arguments)
        if name == "Tuple":
            if not all(isinstance(argument, TypeDescriptor) for argument in arguments):
                raise SerializationError("Tuple arguments must be types")
            return TupleType(cast(tuple[TypeDescriptor, ...], tuple(arguments)))
        if name == "Result":
            if len(arguments) != 2 or not all(
                isinstance(argument, TypeDescriptor) for argument in arguments
            ):
                raise SerializationError("Result expects value and error types")
            typed_arguments = cast(tuple[TypeDescriptor, TypeDescriptor], tuple(arguments))
            return RuntimeType(RuntimeKind.RESULT, *typed_arguments)
        if name in {kind.value for kind in SemanticKind}:
            if len(arguments) not in {1, 2} or not isinstance(arguments[0], TypeDescriptor):
                raise SerializationError(f"{name} expects a value type and optional trust label")
            kind = SemanticKind(name)
            if len(arguments) == 1:
                if kind not in {SemanticKind.GOAL, SemanticKind.CONSTRAINT}:
                    raise SerializationError(f"{name} requires a trust label")
                return SemanticType(kind, arguments[0])
            if not isinstance(arguments[1], TrustLabel):
                raise SerializationError(f"{name} trust argument is invalid")
            return SemanticType(kind, arguments[0], arguments[1])
        raise SerializationError(f"unknown generic type: {name!r}")


def parse_type(text: str) -> TypeDescriptor:
    """Parse the compact canonical type spelling without evaluating code."""

    if not isinstance(text, str) or not text:
        raise SerializationError("type text must be a non-empty string")
    return _TypeParser(text).parse()
