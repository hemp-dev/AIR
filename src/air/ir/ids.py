"""Validated immutable identifiers used by the AIR data model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, cast

from .errors import InvalidIdentifierError

_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")
_RESULT_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")


def _validate_name(raw: str, label: str) -> str:
    if not isinstance(raw, str) or not _NAME_RE.fullmatch(raw):
        raise InvalidIdentifierError(f"invalid {label}: {raw!r}")
    return raw


@dataclass(frozen=True, slots=True)
class ProgramId:
    """Opaque stable identifier for a canonical AIR program."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_name(self.value, "program id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TaskId:
    """Opaque stable identifier for a logical execution task."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_name(self.value, "task id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PatchId:
    """Stable identifier for one proposed state patch."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_name(self.value, "patch id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class OpId:
    """Identifier for one operation in a program."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_name(self.value, "operation id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ResultId:
    """SSA result identifier, canonically stored with its leading ``%``."""

    value: str

    def __post_init__(self) -> None:
        raw = (
            self.value[1:]
            if isinstance(self.value, str) and self.value.startswith("%")
            else self.value
        )
        if not isinstance(raw, str) or not _RESULT_RE.fullmatch(raw):
            raise InvalidIdentifierError(f"invalid result id: {self.value!r}")
        object.__setattr__(self, "value", f"%{raw}")

    @property
    def bare(self) -> str:
        """Return the identifier without the AIR-Text sigil."""

        return self.value[1:]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ActorRef:
    """URI-like actor reference, such as ``agent://planner``."""

    value: str

    def __post_init__(self) -> None:
        raw = self.value
        if (
            not isinstance(raw, str)
            or not raw
            or any(char.isspace() or ord(char) < 32 for char in raw)
        ):
            raise InvalidIdentifierError(f"invalid actor reference: {raw!r}")
        scheme, separator, remainder = raw.partition(":")
        if not separator or not _NAME_RE.fullmatch(scheme) or not remainder:
            raise InvalidIdentifierError(f"invalid actor reference: {raw!r}")
        object.__setattr__(self, "value", raw)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ValueRef:
    """Reference to an SSA result in the same canonical program."""

    result_id: ResultId | str

    def __post_init__(self) -> None:
        if not isinstance(self.result_id, ResultId):
            object.__setattr__(self, "result_id", ResultId(self.result_id))

    @property
    def id(self) -> ResultId:
        """Compatibility alias for the referenced result identifier."""

        return cast(ResultId, self.result_id)

    def __str__(self) -> str:
        return str(self.result_id)


# AIR uses SSA result identifiers as its canonical value identifiers.
ValueId = ResultId
