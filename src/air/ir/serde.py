"""Deterministic AIR-JSON serialization for the canonical in-memory model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from .effects import CapabilitySet, Effect
from .errors import SerializationError
from .ids import ActorRef, OpId, ProgramId, ResultId, TaskId, ValueRef
from .operations import Operation, ResultDecl, SourceLocation
from .program import Program
from .provenance import Provenance
from .task import Task
from .types import TypeDescriptor
from .values import FrozenDict, JsonInput, JsonValue, Literal, Value, thaw_json


def program_to_json_obj(program: Program) -> dict[str, object]:
    """Convert a validated program into ordinary JSON-compatible objects."""

    result: dict[str, object] = {
        "actor": str(program.actor),
        "air_version": program.air_version,
        "capabilities": program.capabilities.to_json_values(),
        "metadata": thaw_json(cast(FrozenDict[str, JsonValue], program.metadata)),
        "operations": [operation_to_json_obj(operation) for operation in program.operations],
        "program_id": str(program.program_id),
    }
    if program.task is not None:
        result["task"] = {
            "goal": value_to_json_obj(program.task.goal) if program.task.goal is not None else None,
            "metadata": program.task.json_metadata(),
            "task_id": str(program.task.task_id),
        }
    return result


def operation_to_json_obj(operation: Operation) -> dict[str, object]:
    result: dict[str, object] = {
        "attributes": thaw_json(cast(FrozenDict[str, JsonValue], operation.attributes)),
        "declared_effects": [effect.to_json_obj() for effect in operation.declared_effects],
        "op_id": str(operation.op_id),
        "opcode": operation.opcode,
        "operands": [value_to_json_obj(operand) for operand in operation.operands],
        "results": [
            {"id": str(declaration.id), "type": str(declaration.type)}
            for declaration in operation.results
        ],
    }
    if operation.source_location is not None:
        result["source_location"] = {
            "column": operation.source_location.column,
            "line": operation.source_location.line,
            "source": operation.source_location.source,
        }
    return result


def value_to_json_obj(value: Value) -> dict[str, object]:
    if isinstance(value, ValueRef):
        return {"id": str(value.result_id), "kind": "ref"}
    literal: dict[str, object] = {
        "kind": "literal",
        "value": thaw_json(cast(JsonValue, value.value)),
    }
    if value.type is not None:
        literal["type"] = str(value.type)
    if value.provenance is not None:
        literal["provenance"] = value.provenance.to_json_obj()
    return literal


def serialize_program(program: Program) -> str:
    """Return canonical compact JSON with stable key ordering."""

    return json.dumps(
        program_to_json_obj(program),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def serialize_program_bytes(program: Program) -> bytes:
    """Return the exact UTF-8 bytes counted by deterministic benchmarks."""

    return serialize_program(program).encode("utf-8")


def deserialize_program(payload: str | bytes | Mapping[str, object]) -> Program:
    """Validate and decode a JSON document or already-parsed JSON object."""

    raw: object
    if isinstance(payload, Mapping):
        raw = dict(payload)
    else:
        try:
            raw = json.loads(
                payload,
                object_pairs_hook=_object_pairs_without_duplicates,
                parse_constant=_reject_constant,
            )
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise SerializationError(f"invalid AIR-JSON: {exc}") from exc
    return program_from_json_obj(raw)


def program_from_json_obj(raw: object) -> Program:
    document = _object(raw, "program")
    _reject_unknown(
        document,
        {"air_version", "program_id", "actor", "operations", "capabilities", "metadata", "task"},
        "program",
    )
    air_version = _required_string(document, "air_version", "program")
    program_id = _required_string(document, "program_id", "program")
    actor = _required_string(document, "actor", "program")
    operations_raw = document.get("operations")
    if not isinstance(operations_raw, list):
        raise SerializationError("program.operations must be an array")
    capabilities_raw = document.get("capabilities", [])
    if not isinstance(capabilities_raw, list) or not all(
        isinstance(item, str) for item in capabilities_raw
    ):
        raise SerializationError("program.capabilities must be an array of strings")
    metadata_raw = document.get("metadata", {})
    if not isinstance(metadata_raw, dict):
        raise SerializationError("program.metadata must be an object")
    task = _task_from_json(document.get("task"))
    try:
        return Program(
            program_id=ProgramId(program_id),
            actor=ActorRef(actor),
            operations=tuple(operation_from_json_obj(item) for item in operations_raw),
            air_version=air_version,
            capabilities=CapabilitySet.from_strings(cast(list[str], capabilities_raw)),
            metadata=cast(Mapping[str, JsonInput], metadata_raw),
            task=task,
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, SerializationError):
            raise
        raise SerializationError(f"invalid AIR program: {exc}") from exc


def operation_from_json_obj(raw: object) -> Operation:
    document = _object(raw, "operation")
    _reject_unknown(
        document,
        {
            "op_id",
            "opcode",
            "results",
            "operands",
            "attributes",
            "declared_effects",
            "source_location",
        },
        "operation",
    )
    op_id = _required_string(document, "op_id", "operation")
    opcode = _required_string(document, "opcode", "operation")
    results_raw = document.get("results", [])
    operands_raw = document.get("operands", [])
    effects_raw = document.get("declared_effects", [])
    attributes_raw = document.get("attributes", {})
    if (
        not isinstance(results_raw, list)
        or not isinstance(operands_raw, list)
        or not isinstance(effects_raw, list)
    ):
        raise SerializationError("operation results, operands and declared_effects must be arrays")
    if not isinstance(attributes_raw, dict):
        raise SerializationError("operation.attributes must be an object")
    source_location = _source_location_from_json(document.get("source_location"))
    try:
        return Operation(
            op_id=OpId(op_id),
            opcode=opcode,
            results=tuple(_result_decl_from_json(item) for item in results_raw),
            operands=tuple(_value_from_json(item) for item in operands_raw),
            attributes=cast(Mapping[str, JsonInput], attributes_raw),
            declared_effects=tuple(Effect.from_json_obj(item) for item in effects_raw),
            source_location=source_location,
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, SerializationError):
            raise
        raise SerializationError(f"invalid AIR operation: {exc}") from exc


def _result_decl_from_json(raw: object) -> ResultDecl:
    document = _object(raw, "result declaration")
    _reject_unknown(document, {"id", "type"}, "result declaration")
    return ResultDecl(
        id=ResultId(_required_string(document, "id", "result declaration")),
        type=TypeDescriptor.from_json(document.get("type")),
    )


def _value_from_json(raw: object) -> Value:
    document = _object(raw, "operand")
    kind = document.get("kind")
    if kind == "ref":
        _reject_unknown(document, {"kind", "id"}, "value reference")
        return ValueRef(_required_string(document, "id", "value reference"))
    if kind == "literal":
        _reject_unknown(document, {"kind", "value", "type", "provenance"}, "literal")
        if "value" not in document:
            raise SerializationError("literal requires value")
        type_raw = document.get("type")
        provenance_raw = document.get("provenance")
        return Literal(
            value=cast(JsonInput, document["value"]),
            type=TypeDescriptor.from_json(type_raw) if type_raw is not None else None,
            provenance=Provenance.from_json_obj(provenance_raw)
            if provenance_raw is not None
            else None,
        )
    raise SerializationError(f"unknown operand kind: {kind!r}")


def _source_location_from_json(raw: object) -> SourceLocation | None:
    if raw is None:
        return None
    document = _object(raw, "source_location")
    _reject_unknown(document, {"line", "column", "source"}, "source_location")
    line = document.get("line")
    column = document.get("column")
    if (
        not isinstance(line, int)
        or isinstance(line, bool)
        or not isinstance(column, int)
        or isinstance(column, bool)
    ):
        raise SerializationError("source_location line and column must be integers")
    source = document.get("source")
    if source is not None and not isinstance(source, str):
        raise SerializationError("source_location source must be a string or null")
    return SourceLocation(line=line, column=column, source=source)


def _task_from_json(raw: object) -> Task | None:
    if raw is None:
        return None
    document = _object(raw, "task")
    _reject_unknown(document, {"task_id", "goal", "metadata"}, "task")
    task_id = _required_string(document, "task_id", "task")
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict):
        raise SerializationError("task.metadata must be an object")
    goal_raw = document.get("goal")
    goal = _value_from_json(goal_raw) if goal_raw is not None else None
    return Task(
        task_id=TaskId(task_id),
        goal=goal,
        metadata=cast(Mapping[str, JsonInput], metadata),
    )


def _object(raw: object, label: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise SerializationError(f"{label} must be an object")
    return raw


def _required_string(document: Mapping[str, object], key: str, label: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise SerializationError(f"{label}.{key} must be a string")
    return value


def _reject_unknown(document: Mapping[str, object], allowed: set[str], label: str) -> None:
    unknown = set(document) - allowed
    if unknown:
        raise SerializationError(f"unknown {label} fields: {sorted(unknown)!r}")


def _object_pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")
