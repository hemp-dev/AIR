"""Deterministic static verification pipeline for canonical AIR programs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from ..ir.effects import CapabilityRule, Effect, EffectKind
from ..ir.ids import ResultId
from ..ir.operations import Operation
from ..ir.program import Program
from ..ir.refs import StateRef, normalize_relative_path, normalize_write_scope
from ..ir.types import (
    BOOL,
    FLOAT,
    INT,
    JSON,
    STRING,
    ListType,
    RuntimeKind,
    RuntimeType,
    SemanticKind,
    SemanticType,
    TypeDescriptor,
)
from ..ir.values import FrozenDict, JsonValue, Literal, ValueRef, thaw_json
from .diagnostics import Diagnostic, Severity, VerificationError, VerificationReport
from .registry import OpcodeRegistry


@dataclass(frozen=True, slots=True)
class VerificationContext:
    """Optional deterministic policy information used during verification."""

    human_authorized_ops: frozenset[str] = field(default_factory=frozenset)
    known_agents: frozenset[str] = field(default_factory=frozenset)
    known_tools: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class VerifiedProgram:
    """Capability-like token proving that a Program passed static verification."""

    program: Program
    report: VerificationReport

    def __post_init__(self) -> None:
        if not self.report.ok:
            raise VerificationError(self.report)


class Verifier:
    """Run structural, SSA, type, effect, capability and trust checks."""

    def __init__(self, registry: OpcodeRegistry | None = None) -> None:
        self.registry = registry or OpcodeRegistry()

    def verify(
        self,
        program: Program,
        context: VerificationContext | None = None,
    ) -> VerificationReport:
        if not isinstance(program, Program):
            return VerificationReport(
                (
                    Diagnostic(
                        "AIR001",
                        Severity.ERROR,
                        "verification requires a canonical Program",
                    ),
                )
            )
        policy = context or VerificationContext()
        diagnostics: list[Diagnostic] = []
        symbols: dict[ResultId, TypeDescriptor] = {}
        for operation in program.operations:
            spec = self.registry.get(operation.opcode)
            if spec is None:
                diagnostics.append(
                    self._diagnostic(
                        "AIR002",
                        "unknown opcode",
                        operation,
                        f"unknown opcode: {operation.opcode}",
                    )
                )
                continue
            if not spec.accepts_result_count(len(operation.results)):
                diagnostics.append(
                    self._diagnostic(
                        "AIR001",
                        "invalid result arity",
                        operation,
                        f"{operation.opcode} expects "
                        f"{spec.min_results}..{spec.max_results} results",
                    )
                )
            if not spec.accepts_operand_count(len(operation.operands)):
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "invalid operand arity",
                        operation,
                        f"{operation.opcode} received {len(operation.operands)} operands",
                    )
                )
            operand_types = self._resolve_operands(operation, symbols, diagnostics)
            self._check_operation_shape(operation, operand_types, diagnostics, policy)
            inferred = self._inferred_effects(operation, diagnostics)
            self._check_effects(program, operation, inferred, diagnostics, policy)
            self._check_trust(operation, operand_types, diagnostics)
            self._check_read_scope(operation, diagnostics)
            self._check_write_scope(operation, diagnostics)
            for declaration in operation.results:
                result_id = cast(ResultId, declaration.id)
                result_type = cast(TypeDescriptor, declaration.type)
                symbols[result_id] = result_type
        return VerificationReport(tuple(diagnostics))

    def require_valid(
        self,
        program: Program,
        context: VerificationContext | None = None,
    ) -> VerifiedProgram:
        report = self.verify(program, context)
        return VerifiedProgram(program, report)

    def _resolve_operands(
        self,
        operation: Operation,
        symbols: Mapping[ResultId, TypeDescriptor],
        diagnostics: list[Diagnostic],
    ) -> tuple[TypeDescriptor | None, ...]:
        resolved: list[TypeDescriptor | None] = []
        for operand in operation.operands:
            if isinstance(operand, ValueRef):
                result_id = operand.id
                if result_id not in symbols:
                    diagnostics.append(
                        self._diagnostic(
                            "AIR004",
                            "undefined SSA result",
                            operation,
                            f"undefined result reference: {result_id}",
                            (str(result_id),),
                        )
                    )
                    resolved.append(None)
                else:
                    resolved.append(symbols[result_id])
            elif isinstance(operand, Literal):
                resolved.append(
                    cast(TypeDescriptor, operand.type)
                    if operand.type is not None
                    else _infer_literal_type(cast(JsonValue, operand.value))
                )
            else:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "unsupported operand",
                        operation,
                        f"unsupported operand value: {operand!r}",
                    )
                )
                resolved.append(None)
        return tuple(resolved)

    def _check_operation_shape(
        self,
        operation: Operation,
        operand_types: Sequence[TypeDescriptor | None],
        diagnostics: list[Diagnostic],
        context: VerificationContext,
    ) -> None:
        opcode = operation.opcode
        if opcode in {"state.read", "state.project", "state.patch", "state.commit"}:
            ref_value = _attribute_string(operation, "ref") or _attribute_string(
                operation, "target"
            )
            if ref_value is not None:
                try:
                    StateRef.parse(ref_value)
                except ValueError as exc:
                    diagnostics.append(
                        self._diagnostic("AIR009", "invalid state reference", operation, str(exc))
                    )
            elif opcode in {"state.read", "state.project", "state.patch", "state.commit"}:
                diagnostics.append(
                    self._diagnostic(
                        "AIR009",
                        "missing state reference",
                        operation,
                        f"{opcode} requires ref/target",
                    )
                )
        if opcode in {"state.patch", "state.commit"}:
            if operation.attribute("base_version") is None and opcode == "state.patch":
                diagnostics.append(
                    self._diagnostic(
                        "AIR011",
                        "state version missing",
                        operation,
                        "state.patch requires base_version",
                    )
                )
            if not _attribute_strings(operation, "write_set"):
                diagnostics.append(
                    self._diagnostic(
                        "AIR010",
                        "write set missing",
                        operation,
                        f"{opcode} requires write_set",
                    )
                )
            if opcode == "state.patch" and not (
                _attribute_object(operation, "writes") or _attribute_string(operation, "path")
            ):
                diagnostics.append(
                    self._diagnostic(
                        "AIR010",
                        "patch content missing",
                        operation,
                        "state.patch requires writes or path",
                    )
                )
        if opcode in {"state.read", "state.project"}:
            if opcode == "state.project" and not _attribute_strings(operation, "fields"):
                diagnostics.append(
                    self._diagnostic(
                        "AIR009",
                        "missing projection fields",
                        operation,
                        "state.project requires a non-empty fields list",
                    )
                )
            if operation.results:
                result_type = cast(TypeDescriptor, operation.results[0].type)
                if not isinstance(result_type, RuntimeType) or result_type.kind != RuntimeKind.REF:
                    diagnostics.append(
                        self._diagnostic(
                            "AIR005",
                            "state read result type mismatch",
                            operation,
                            "state.read/state.project must return Ref<T>",
                        )
                    )
        if (
            opcode in {"core.fact", "core.claim", "core.goal", "core.constraint"}
            and operation.results
        ):
            expected_kinds = {
                "core.fact": SemanticKind.FACT,
                "core.claim": SemanticKind.CLAIM,
                "core.goal": SemanticKind.GOAL,
                "core.constraint": SemanticKind.CONSTRAINT,
            }
            result_type = cast(TypeDescriptor, operation.results[0].type)
            if (
                not isinstance(result_type, SemanticType)
                or result_type.kind != expected_kinds[opcode]
            ):
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "semantic result type mismatch",
                        operation,
                        f"{opcode} must produce {expected_kinds[opcode].value}<T>",
                    )
                )
            elif operand_types and not _types_compatible(
                operand_types[0], cast(SemanticType, result_type).value
            ):
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "semantic operand type mismatch",
                        operation,
                        f"operand type {operand_types[0]} does not match "
                        f"semantic value type {cast(SemanticType, result_type).value}",
                    )
                )
        elif opcode == "state.patch" and operation.results:
            result_type = cast(TypeDescriptor, operation.results[0].type)
            if not isinstance(result_type, RuntimeType) or result_type.kind != RuntimeKind.PATCH:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "state.patch result type mismatch",
                        operation,
                        "state.patch must return Patch<T>",
                    )
                )
        elif opcode == "state.diff" and operation.results:
            result_type = cast(TypeDescriptor, operation.results[0].type)
            if result_type != JSON:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "state diff result type mismatch",
                        operation,
                        "state.diff must return Json",
                    )
                )
        elif opcode == "state.commit" and operation.results:
            result_type = cast(TypeDescriptor, operation.results[0].type)
            if not isinstance(result_type, RuntimeType) or result_type.kind != RuntimeKind.SNAPSHOT:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "state.commit result type mismatch",
                        operation,
                        "state.commit must return Snapshot<T> when it has a result",
                    )
                )
        if opcode == "state.commit":
            if len(operand_types) != 1 or not _is_runtime_kind(operand_types[0], RuntimeKind.PATCH):
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "state.commit operand type mismatch",
                        operation,
                        "state.commit requires exactly one Patch<T> operand",
                    )
                )
        elif opcode == "verify.assert":
            if len(operand_types) != 1 or operand_types[0] != BOOL:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "assertion operand type mismatch",
                        operation,
                        "verify.assert requires exactly one Bool operand",
                    )
                )
        elif opcode == "verify.check":
            if not operand_types:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "verification input missing",
                        operation,
                        "verify.check requires an input operand",
                    )
                )
            verifier_name = _attribute_string(operation, "verifier")
            if not verifier_name:
                diagnostics.append(
                    self._diagnostic(
                        "AIR008",
                        "verification method missing",
                        operation,
                        "verify.check requires a named verifier",
                    )
                )
            if operation.results:
                result_type = cast(TypeDescriptor, operation.results[0].type)
                if isinstance(result_type, SemanticType) and result_type.trust is not None:
                    if cast(str, result_type.trust) != "Verified":
                        diagnostics.append(
                            self._diagnostic(
                                "AIR008",
                                "verify.check must produce Verified or a non-trust runtime result",
                                operation,
                                f"invalid verification output trust: {result_type.trust}",
                            )
                        )
        elif opcode in {"agent.invoke", "agent.spawn"}:
            actor = _attribute_string(operation, "actor")
            if not actor:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005", "agent target missing", operation, "agent.invoke requires actor"
                    )
                )
            elif context.known_agents and actor not in context.known_agents:
                diagnostics.append(
                    self._diagnostic(
                        "AIR013", "unknown agent backend", operation, f"unknown agent: {actor}"
                    )
                )
            if opcode == "agent.spawn" and operation.results:
                result_type = cast(TypeDescriptor, operation.results[0].type)
                if not isinstance(result_type, RuntimeType) or (
                    result_type.kind != RuntimeKind.FUTURE
                ):
                    diagnostics.append(
                        self._diagnostic(
                            "AIR005",
                            "future result type mismatch",
                            operation,
                            "agent.spawn must return Future<T>",
                        )
                    )
        elif opcode == "agent.await":
            if operand_types and isinstance(operand_types[0], RuntimeType):
                future_type = operand_types[0]
                if future_type.kind != RuntimeKind.FUTURE:
                    diagnostics.append(
                        self._diagnostic(
                            "AIR005",
                            "await operand type mismatch",
                            operation,
                            "agent.await requires Future<T>",
                        )
                    )
                elif operation.results:
                    result_type = cast(TypeDescriptor, operation.results[0].type)
                    if not _types_compatible(result_type, future_type.value):
                        diagnostics.append(
                            self._diagnostic(
                                "AIR005",
                                "await result type mismatch",
                                operation,
                                f"agent.await must return {future_type.value}",
                            )
                        )
            elif operand_types:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "await operand type mismatch",
                        operation,
                        "agent.await requires Future<T>",
                    )
                )
        elif opcode == "agent.join":
            future_types = [item for item in operand_types if isinstance(item, RuntimeType)]
            if (
                not future_types
                or len(future_types) != len(operand_types)
                or any(item.kind != RuntimeKind.FUTURE for item in future_types)
            ):
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "join operand type mismatch",
                        operation,
                        "agent.join requires one or more Future<T> operands",
                    )
                )
            elif operation.results:
                result_type = cast(TypeDescriptor, operation.results[0].type)
                expected = ListType(future_types[0].value)
                if any(
                    not _types_compatible(item.value, future_types[0].value)
                    for item in future_types
                ):
                    diagnostics.append(
                        self._diagnostic(
                            "AIR005",
                            "join future type mismatch",
                            operation,
                            "agent.join futures must have compatible value types",
                        )
                    )
                elif not _types_compatible(result_type, expected):
                    diagnostics.append(
                        self._diagnostic(
                            "AIR005",
                            "join result type mismatch",
                            operation,
                            f"agent.join must return {expected}",
                        )
                    )
        elif opcode == "tool.call":
            tool = _attribute_string(operation, "tool")
            if not tool:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005", "tool target missing", operation, "tool.call requires tool"
                    )
                )
            elif context.known_tools and tool not in context.known_tools:
                diagnostics.append(
                    self._diagnostic(
                        "AIR013", "unknown tool backend", operation, f"unknown tool: {tool}"
                    )
                )
        elif opcode == "human.request" and operation.results:
            result_type = cast(TypeDescriptor, operation.results[0].type)
            if result_type != BOOL:
                diagnostics.append(
                    self._diagnostic(
                        "AIR005",
                        "human request result type mismatch",
                        operation,
                        "human.request must return Bool when it has a result",
                    )
                )

    def _inferred_effects(
        self,
        operation: Operation,
        diagnostics: list[Diagnostic],
    ) -> tuple[Effect, ...]:
        opcode = operation.opcode
        effects: list[Effect] = []
        if opcode in {"state.read", "state.project"}:
            resource = _attribute_string(operation, "ref")
            if resource:
                effects.append(Effect(EffectKind.READ, resource))
        elif opcode == "state.commit":
            target = _attribute_string(operation, "target")
            for path in _attribute_strings(operation, "write_set"):
                if target:
                    effects.append(Effect(EffectKind.WRITE, f"{target}/{path}"))
        elif opcode in {"agent.invoke", "agent.spawn"}:
            actor = _attribute_string(operation, "actor")
            if actor:
                effects.append(Effect(EffectKind.SEND, actor))
        elif opcode == "tool.call":
            tool = _attribute_string(operation, "tool")
            if tool:
                effects.append(Effect(EffectKind.TOOL, tool))
        elif opcode == "human.notify":
            effects.append(Effect(EffectKind.HUMAN, "notify"))
        elif opcode == "human.request":
            effects.append(Effect(EffectKind.HUMAN, "request"))
        return tuple(effects)

    def _check_effects(
        self,
        program: Program,
        operation: Operation,
        inferred: Sequence[Effect],
        diagnostics: list[Diagnostic],
        context: VerificationContext,
    ) -> None:
        declared = tuple(operation.declared_effects)
        for effect in declared:
            if effect.kind == EffectKind.CUSTOM:
                diagnostics.append(
                    self._diagnostic(
                        "AIR006",
                        "unknown effect",
                        operation,
                        f"custom effects are denied by default: {effect}",
                    )
                )
        for effect in inferred:
            if not any(_effect_covers(candidate, effect) for candidate in declared):
                diagnostics.append(
                    self._diagnostic(
                        "AIR006",
                        "inferred effect not declared",
                        operation,
                        f"missing declared effect: {effect}",
                        (effect.resource,),
                    )
                )
        for effect in declared:
            if not program.capabilities.allows(effect):
                diagnostics.append(
                    self._diagnostic(
                        "AIR007",
                        "capability denied",
                        operation,
                        f"actor is not allowed to perform {effect}",
                        (effect.resource,),
                    )
                )
        risky = tuple(
            effect for effect in declared if effect.kind in {EffectKind.MONEY, EffectKind.EGRESS}
        )
        if risky and str(operation.op_id) not in context.human_authorized_ops:
            diagnostics.append(
                self._diagnostic(
                    "AIR014",
                    "human authorization required",
                    operation,
                    "money and egress effects require explicit human authorization",
                    tuple(effect.resource for effect in risky),
                )
            )

    def _check_trust(
        self,
        operation: Operation,
        operand_types: Sequence[TypeDescriptor | None],
        diagnostics: list[Diagnostic],
    ) -> None:
        for declaration in operation.results:
            result_type = cast(TypeDescriptor, declaration.type)
            if not isinstance(result_type, SemanticType) or result_type.trust is None:
                continue
            trust = cast(str, result_type.trust)
            if trust == "Verified" and operation.opcode != "verify.check":
                diagnostics.append(
                    self._diagnostic(
                        "AIR008",
                        "implicit trust escalation",
                        operation,
                        "only verify.check may produce a Verified semantic value",
                    )
                )
            if trust == "Verified" and operation.opcode == "verify.check":
                if not any(_is_unverified_type(item) for item in operand_types if item is not None):
                    diagnostics.append(
                        self._diagnostic(
                            "AIR008",
                            "verification input is not trust-bearing",
                            operation,
                            "verify.check requires a typed semantic input",
                        )
                    )

    def _check_write_scope(self, operation: Operation, diagnostics: list[Diagnostic]) -> None:
        if operation.opcode not in {"state.patch", "state.commit"}:
            return
        writes = _attribute_object(operation, "writes")
        if not writes:
            path = _attribute_string(operation, "path")
            if path is not None:
                writes = {path: None}
        declared_raw = _attribute_strings(operation, "write_set")
        declared: list[str] = []
        for scope in declared_raw:
            try:
                declared.append(normalize_write_scope(scope))
            except ValueError as exc:
                diagnostics.append(
                    self._diagnostic("AIR010", "invalid write scope", operation, str(exc), (scope,))
                )
        normalized_writes: list[tuple[str, str]] = []
        for path in writes:
            try:
                normalized_writes.append((path, normalize_relative_path(path)))
            except ValueError as exc:
                diagnostics.append(
                    self._diagnostic("AIR010", "invalid write path", operation, str(exc), (path,))
                )
        if writes and not declared:
            diagnostics.append(
                self._diagnostic(
                    "AIR010",
                    "write set missing",
                    operation,
                    "state patch/commit requires write_set",
                )
            )
        for original_path, path in normalized_writes:
            if not any(_write_path_allowed(path, scope) for scope in declared):
                diagnostics.append(
                    self._diagnostic(
                        "AIR010",
                        "write outside declared scope",
                        operation,
                        f"write path {original_path!r} is outside {declared!r}",
                        (original_path,),
                    )
                )

    def _check_read_scope(self, operation: Operation, diagnostics: list[Diagnostic]) -> None:
        if operation.opcode not in {"state.read", "state.project"}:
            return
        resource = _attribute_string(operation, "ref")
        scopes = _attribute_strings(operation, "read_set")
        if resource is None:
            return
        resource_scopes = tuple(scope for scope in scopes if scope.startswith("wm://"))
        field_scopes = tuple(scope for scope in scopes if not scope.startswith("wm://"))
        resource_outside_scope = resource_scopes and not any(
            _resource_in_scope(resource, scope) for scope in resource_scopes
        )
        if resource_outside_scope or (
            operation.opcode == "state.read" and scopes and not resource_scopes
        ):
            diagnostics.append(
                self._diagnostic(
                    "AIR007",
                    "read outside declared scope",
                    operation,
                    f"read resource {resource!r} is outside {scopes!r}",
                    (resource,),
                )
            )
        fields = _attribute_strings(operation, "fields")
        for field_path in fields:
            try:
                normalized_field = normalize_relative_path(field_path)
            except ValueError as exc:
                diagnostics.append(
                    self._diagnostic(
                        "AIR007", "invalid read path", operation, str(exc), (field_path,)
                    )
                )
                continue
            if field_scopes and not any(
                _write_path_allowed(normalized_field, scope) for scope in field_scopes
            ):
                diagnostics.append(
                    self._diagnostic(
                        "AIR007",
                        "read field outside declared scope",
                        operation,
                        f"read field {field_path!r} is outside {scopes!r}",
                        (field_path,),
                    )
                )

    @staticmethod
    def _diagnostic(
        code: str,
        _category: str,
        operation: Operation,
        message: str,
        related_refs: tuple[str, ...] = (),
    ) -> Diagnostic:
        return Diagnostic(
            code,
            Severity.ERROR,
            message,
            str(operation.op_id),
            operation.source_location,
            related_refs,
        )


def _attribute_string(operation: Operation, name: str) -> str | None:
    value = operation.attribute(name)
    return value if isinstance(value, str) else None


def _attribute_strings(operation: Operation, name: str) -> tuple[str, ...]:
    value = operation.attribute(name)
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _attribute_object(operation: Operation, name: str) -> Mapping[str, object]:
    value = operation.attribute(name)
    if isinstance(value, FrozenDict):
        raw = thaw_json(value)
        return raw if isinstance(raw, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _infer_literal_type(value: JsonValue) -> TypeDescriptor:
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return FLOAT
    if isinstance(value, str):
        return STRING
    return JSON


def _is_unverified_type(type_descriptor: TypeDescriptor) -> bool:
    return (
        isinstance(type_descriptor, SemanticType)
        and type_descriptor.trust is not None
        and cast(str, type_descriptor.trust) != "Verified"
    )


def _is_runtime_kind(type_descriptor: TypeDescriptor | None, kind: RuntimeKind) -> bool:
    return isinstance(type_descriptor, RuntimeType) and type_descriptor.kind == kind


def _types_compatible(actual: TypeDescriptor | None, expected: TypeDescriptor) -> bool:
    """Use exact structural equality for the MVP type compatibility rule."""

    return actual is not None and actual == expected


def _effect_covers(declared: Effect, inferred: Effect) -> bool:
    return CapabilityRule(declared.kind, declared.resource).matches(inferred)


def _write_path_allowed(path: str, scope: str) -> bool:
    if scope.endswith("/*"):
        scope = f"{scope[:-2]}.*"
    return path == scope or (scope.endswith(".*") and path.startswith(scope[:-2] + "."))


def _resource_in_scope(resource: str, scope: str) -> bool:
    if resource == scope:
        return True
    if scope.endswith("/**"):
        base = scope[:-3].rstrip("/")
        return resource.startswith(base + "/")
    if scope.endswith("/*"):
        base = scope[:-2].rstrip("/")
        return resource.startswith(base + "/") and "/" not in resource[len(base) + 1 :]
    return False
