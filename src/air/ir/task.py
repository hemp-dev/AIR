"""Immutable task metadata attached to a canonical AIR program."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from .ids import TaskId
from .values import FrozenDict, JsonInput, JsonValue, Value, freeze_json, thaw_json


@dataclass(frozen=True, slots=True)
class Task:
    """Observable task identity, optional goal value and metadata."""

    task_id: TaskId | str
    goal: Value | None = None
    metadata: FrozenDict[str, JsonValue] | Mapping[str, JsonInput] = field(
        default_factory=FrozenDict
    )

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            object.__setattr__(self, "task_id", TaskId(self.task_id))
        frozen_metadata = freeze_json(self.metadata)
        if not isinstance(frozen_metadata, FrozenDict):
            raise ValueError("task metadata must be a JSON object")
        object.__setattr__(self, "metadata", frozen_metadata)

    def json_metadata(self) -> dict[str, object]:
        frozen = cast(FrozenDict[str, JsonValue], self.metadata)
        return cast(dict[str, object], thaw_json(frozen))
