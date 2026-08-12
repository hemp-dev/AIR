"""Canonical references to immutable shared semantic state."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidIdentifierError

_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]+\Z")


@dataclass(frozen=True, slots=True)
class StateRef:
    """Normalized ``wm://namespace/path[#object-id]`` state reference."""

    namespace: str
    path: tuple[str, ...]
    object_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, str) or _SEGMENT_RE.fullmatch(self.namespace) is None:
            raise InvalidIdentifierError(f"invalid state namespace: {self.namespace!r}")
        normalized_path = tuple(self.path)
        if not normalized_path or any(
            not isinstance(segment, str) or _SEGMENT_RE.fullmatch(segment) is None
            for segment in normalized_path
        ):
            raise InvalidIdentifierError(f"invalid state path: {self.path!r}")
        if self.object_id is not None:
            if not isinstance(self.object_id, str) or _SEGMENT_RE.fullmatch(self.object_id) is None:
                raise InvalidIdentifierError(f"invalid state object id: {self.object_id!r}")
        object.__setattr__(self, "path", normalized_path)

    @classmethod
    def parse(cls, raw: str | StateRef) -> StateRef:
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, str) or not raw.startswith("wm://"):
            raise InvalidIdentifierError(f"invalid state reference: {raw!r}")
        if any(char.isspace() or ord(char) < 32 for char in raw):
            raise InvalidIdentifierError(f"invalid state reference: {raw!r}")
        without_scheme = raw[5:]
        authority_and_path, separator, object_id = without_scheme.partition("#")
        if separator and not object_id:
            raise InvalidIdentifierError(f"invalid state reference: {raw!r}")
        namespace, slash, path_text = authority_and_path.partition("/")
        if (
            not slash
            or not path_text
            or any(segment in {".", ".."} for segment in path_text.split("/"))
        ):
            raise InvalidIdentifierError(f"invalid state reference: {raw!r}")
        return cls(
            namespace=namespace, path=tuple(path_text.split("/")), object_id=object_id or None
        )

    @property
    def base(self) -> StateRef:
        """Return the named reference without an immutable object fragment."""

        return StateRef(self.namespace, self.path)

    @property
    def uri(self) -> str:
        """Return the normalized full URI."""

        value = f"wm://{self.namespace}/{'/'.join(self.path)}"
        return f"{value}#{self.object_id}" if self.object_id is not None else value

    def with_object_id(self, object_id: str) -> StateRef:
        return StateRef(self.namespace, self.path, object_id)

    def child(self, relative_path: str) -> str:
        """Return a normalized resource URI for a relative dot path."""

        segments = _normalize_relative_path(relative_path)
        return f"{self.base.uri}/{'/'.join(segments)}"

    def __str__(self) -> str:
        return self.uri


def normalize_relative_path(raw: str) -> str:
    """Normalize a state field path and reject traversal-like components."""

    return ".".join(_normalize_relative_path(raw))


def normalize_write_scope(raw: str) -> str:
    """Normalize an exact path or a child scope ending in ``.*``/``/*``."""

    if isinstance(raw, str) and raw.endswith((".*", "/*")):
        suffix = raw[-2:]
        return f"{normalize_relative_path(raw[:-2])}.*" if suffix in {".*", "/*"} else raw
    return normalize_relative_path(raw)


def _normalize_relative_path(raw: str) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw:
        raise InvalidIdentifierError(f"invalid relative state path: {raw!r}")
    segments = tuple(raw.split("/") if "/" in raw else raw.split("."))
    if not segments or any(segment in {"", ".", ".."} for segment in segments):
        raise InvalidIdentifierError(f"invalid relative state path: {raw!r}")
    if any(_SEGMENT_RE.fullmatch(segment) is None for segment in segments):
        raise InvalidIdentifierError(f"invalid relative state path: {raw!r}")
    return segments
