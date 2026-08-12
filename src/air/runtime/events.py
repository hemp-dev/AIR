"""Append-only structured runtime event log."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from ..ir.values import FrozenDict, JsonInput, JsonValue, freeze_json, thaw_json


@dataclass(frozen=True, slots=True)
class Event:
    """One observable runtime transition."""

    event_id: int
    run_id: str
    event_type: str
    op_id: str | None = None
    payload: FrozenDict[str, JsonValue] | Mapping[str, JsonInput] = field(
        default_factory=FrozenDict
    )
    refs: tuple[str, ...] = field(default_factory=tuple)
    monotonic_ns: int | None = None

    def __post_init__(self) -> None:
        if self.event_id < 1:
            raise ValueError("event ids start at one")
        if not self.run_id or not self.event_type:
            raise ValueError("events require run_id and event_type")
        frozen = freeze_json(self.payload)
        if not isinstance(frozen, FrozenDict):
            raise ValueError("event payload must be a JSON object")
        object.__setattr__(self, "payload", frozen)
        object.__setattr__(self, "refs", tuple(self.refs))

    def json_payload(self) -> dict[str, object]:
        frozen = cast(FrozenDict[str, JsonValue], self.payload)
        return cast(dict[str, object], thaw_json(frozen))


class EventLog:
    """Mutable append-only collector owned by the runtime."""

    def __init__(self, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self.run_id = run_id
        self._events: list[Event] = []

    def append(
        self,
        event_type: str,
        *,
        op_id: str | None = None,
        payload: Mapping[str, JsonInput] | None = None,
        refs: tuple[str, ...] = (),
        monotonic_ns: int | None = None,
    ) -> Event:
        event = Event(
            event_id=len(self._events) + 1,
            run_id=self.run_id,
            event_type=event_type,
            op_id=op_id,
            payload=payload or {},
            refs=refs,
            monotonic_ns=monotonic_ns,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)
