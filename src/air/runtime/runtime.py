"""Small sequential AIR execution runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ..backends.base import AgentExecutor, BackendRequest, ToolExecutor
from ..ir.ids import ActorRef, OpId, ResultId, ValueRef
from ..ir.operations import Operation
from ..ir.program import Program
from ..ir.provenance import Provenance
from ..ir.refs import StateRef, normalize_write_scope
from ..ir.types import RuntimeKind, RuntimeType, TypeDescriptor
from ..ir.values import FrozenDict, JsonInput, JsonValue, Literal, thaw_json
from ..state import (
    InvalidPatchError,
    Patch,
    PatchIntegrityError,
    StaleVersionError,
    StateError,
    StateObject,
    StateProjection,
    StateStore,
    WriteScopeError,
)
from ..verifier import VerificationContext, VerificationReport, VerifiedProgram, Verifier
from .errors import (
    AssertionFailure,
    BackendFailure,
    HumanRequired,
    RuntimeErrorBase,
    StateFailure,
    UnknownRuntimeOperation,
)
from .events import Event, EventLog
from .futures import FutureValue


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Top-level result of one runtime run."""

    success: bool
    run_id: str
    values: Mapping[ResultId, object]
    events: tuple[Event, ...]
    verification: VerificationReport
    failure: RuntimeErrorBase | None = None


class Runtime:
    """Verify and execute canonical AIR programs sequentially."""

    def __init__(
        self,
        state_store: StateStore,
        *,
        verifier: Verifier | None = None,
        agent_executor: AgentExecutor | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.state_store = state_store
        self.verifier = verifier or Verifier()
        self.agent_executor = agent_executor
        self.tool_executor = tool_executor

    def execute(
        self,
        program: Program | VerifiedProgram,
        *,
        run_id: str | None = None,
        context: VerificationContext | None = None,
        human_approvals: frozenset[str] = frozenset(),
    ) -> ExecutionResult:
        candidate = program.program if isinstance(program, VerifiedProgram) else program
        actual_run_id = run_id or (
            str(candidate.task.task_id) if candidate.task else str(candidate.program_id)
        )
        log = EventLog(actual_run_id)
        report = (
            program.report
            if isinstance(program, VerifiedProgram)
            else self.verifier.verify(candidate, context)
        )
        values: dict[ResultId, object] = {}
        if not report.ok:
            for diagnostic in report.errors:
                log.append(
                    "verification.rejected",
                    op_id=diagnostic.op_id,
                    payload={"code": diagnostic.code, "message": diagnostic.message},
                    refs=diagnostic.related_refs,
                )
            log.append("task.failed", payload={"reason": "verification"})
            return ExecutionResult(False, actual_run_id, values, log.events, report)
        log.append("task.started", payload={"program_id": str(candidate.program_id)})
        current_op: Operation | None = None
        try:
            for operation in candidate.operations:
                current_op = operation
                op_id = str(operation.op_id)
                log.append("op.started", op_id=op_id, payload={"opcode": operation.opcode})
                result = self._dispatch(candidate, operation, values, log, human_approvals)
                for declaration, runtime_value in zip(operation.results, result, strict=True):
                    values[cast(ResultId, declaration.id)] = runtime_value
                log.append(
                    "op.completed",
                    op_id=op_id,
                    payload={"opcode": operation.opcode, "result_count": len(result)},
                )
            log.append("task.completed", payload={"program_id": str(candidate.program_id)})
            return ExecutionResult(True, actual_run_id, dict(values), log.events, report)
        except RuntimeErrorBase as exc:
            log.append(
                "op.failed",
                op_id=str(current_op.op_id) if current_op is not None else None,
                payload={
                    "code": _runtime_error_code(exc),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            log.append("task.failed", payload={"reason": type(exc).__name__})
            return ExecutionResult(False, actual_run_id, dict(values), log.events, report, exc)
        except StateError as exc:
            failure = StateFailure(exc)
            event_type = (
                "state.conflict" if isinstance(exc, StaleVersionError) else "state.patch.rejected"
            )
            payload: dict[str, JsonInput] = {
                "code": _state_error_code(exc),
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            if isinstance(exc, StaleVersionError):
                payload.update({"expected": exc.expected, "actual": exc.actual})
            log.append(
                event_type,
                op_id=str(current_op.op_id) if current_op is not None else None,
                payload=payload,
            )
            log.append(
                "op.failed",
                op_id=str(current_op.op_id) if current_op is not None else None,
                payload={
                    "code": _state_error_code(exc),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            log.append("task.failed", payload={"reason": type(exc).__name__})
            return ExecutionResult(False, actual_run_id, dict(values), log.events, report, failure)
        except Exception as exc:
            uncontrolled_failure = BackendFailure(f"uncontrolled runtime failure: {exc}")
            log.append(
                "op.failed",
                op_id=str(current_op.op_id) if current_op is not None else None,
                payload={
                    "code": "AIR013",
                    "error_type": type(uncontrolled_failure).__name__,
                    "message": str(uncontrolled_failure),
                },
            )
            log.append(
                "task.failed",
                payload={
                    "reason": type(uncontrolled_failure).__name__,
                    "message": str(uncontrolled_failure),
                },
            )
            return ExecutionResult(
                False,
                actual_run_id,
                dict(values),
                log.events,
                report,
                uncontrolled_failure,
            )

    def _dispatch(
        self,
        program: Program,
        operation: Operation,
        values: Mapping[ResultId, object],
        log: EventLog,
        human_approvals: frozenset[str],
    ) -> tuple[object, ...]:
        opcode = operation.opcode
        if opcode in {"core.fact", "core.claim", "core.goal", "core.constraint"}:
            return (self._semantic_literal(program, operation, values),)
        if opcode == "state.read":
            snapshot = self.state_store.read(_required_attr(operation, "ref"))
            log.append("state.read", op_id=str(operation.op_id), refs=(str(snapshot.ref),))
            return (snapshot,)
        if opcode == "state.project":
            projection = self.state_store.project(
                _required_attr(operation, "ref"), _attribute_strings(operation, "fields")
            )
            log.append(
                "state.projected",
                op_id=str(operation.op_id),
                payload={"materialized_bytes": projection.materialized_bytes},
                refs=(str(projection.source_ref),),
            )
            return (projection,)
        if opcode == "state.diff":
            left, right = self._operands(operation, values)[:2]
            diff = cast(JsonInput, _diff_values(_json_value(left), _json_value(right)))
            return (Literal(diff, JSON_TYPE),)
        if opcode == "state.patch":
            patch = self._make_patch(program, operation, values)
            target = cast(StateRef, patch.target)
            log.append(
                "state.patch.proposed",
                op_id=str(operation.op_id),
                payload={"paths": list(patch.changed_paths)},
                refs=(str(target.base),),
            )
            return (patch,)
        if opcode == "state.commit":
            patch = cast(Patch, self._require_value(operation, values, 0, Patch))
            self._validate_commit_contract(operation, patch)
            snapshot = self.state_store.commit(patch)
            log.append(
                "state.commit",
                op_id=str(operation.op_id),
                payload={"version": snapshot.version, "paths": list(patch.changed_paths)},
                refs=(str(snapshot.ref),),
            )
            return (snapshot,) if operation.results else ()
        if opcode == "agent.invoke":
            if self.agent_executor is None:
                raise BackendFailure("agent executor is not configured")
            request = BackendRequest(
                _required_attr(operation, "actor"),
                self._operands(operation, values)[0] if operation.operands else None,
                str(operation.op_id),
            )
            log.append(
                "agent.called",
                op_id=str(operation.op_id),
                payload={"actor": request.target},
            )
            response = self.agent_executor.invoke(request)
            log.append(
                "agent.completed",
                op_id=str(operation.op_id),
                payload={"actor": request.target},
            )
            return (self._coerce_backend_value(response, operation),)
        if opcode == "agent.spawn":
            if self.agent_executor is None:
                raise BackendFailure("agent executor is not configured")
            request = BackendRequest(
                _required_attr(operation, "actor"),
                self._operands(operation, values)[0] if operation.operands else None,
                str(operation.op_id),
            )
            log.append(
                "agent.spawned",
                op_id=str(operation.op_id),
                payload={"actor": request.target, "future_id": str(operation.op_id)},
            )
            response = self.agent_executor.invoke(request)
            future_type = cast(TypeDescriptor, operation.results[0].type)
            if not isinstance(future_type, RuntimeType) or future_type.kind != RuntimeKind.FUTURE:
                raise BackendFailure("agent.spawn requires Future<T> result type")
            result = self._coerce_backend_value(response, operation, result_type=future_type.value)
            future = FutureValue(str(operation.op_id), request.target, result)
            log.append(
                "agent.completed",
                op_id=str(operation.op_id),
                payload={"actor": request.target, "future_id": future.future_id},
            )
            return (future,)
        if opcode == "agent.await":
            future = cast(FutureValue, self._require_value(operation, values, 0, FutureValue))
            log.append(
                "agent.awaited",
                op_id=str(operation.op_id),
                payload={"future_id": future.future_id, "actor": future.target},
            )
            return (future.result,)
        if opcode == "agent.join":
            futures = tuple(
                cast(FutureValue, value)
                for value in self._operands(operation, values)
                if isinstance(value, FutureValue)
            )
            if len(futures) != len(operation.operands):
                raise BackendFailure("agent.join operands must be Future values")
            result_type = cast(TypeDescriptor, operation.results[0].type)
            joined = [cast(JsonInput, _json_value(future.result)) for future in futures]
            log.append(
                "agent.joined",
                op_id=str(operation.op_id),
                payload={"future_ids": [future.future_id for future in futures]},
            )
            return (Literal(joined, result_type),)
        if opcode == "tool.call":
            if self.tool_executor is None:
                raise BackendFailure("tool executor is not configured")
            request = BackendRequest(
                _required_attr(operation, "tool"),
                self._operands(operation, values)[0] if operation.operands else None,
                str(operation.op_id),
            )
            log.append(
                "tool.called",
                op_id=str(operation.op_id),
                payload={"tool": request.target},
            )
            response = self.tool_executor.call(request)
            log.append(
                "tool.completed",
                op_id=str(operation.op_id),
                payload={"tool": request.target},
            )
            return (self._coerce_backend_value(response, operation),)
        if opcode == "verify.check":
            source = self._operands(operation, values)[0]
            return (self._verified_value(program, operation, source),)
        if opcode == "verify.assert":
            condition = self._operands(operation, values)[0]
            if not isinstance(condition, Literal) or condition.value is not True:
                raise AssertionFailure(f"verify.assert failed at {operation.op_id}")
            return ()
        if opcode == "human.notify":
            log.append(
                "human.notify",
                op_id=str(operation.op_id),
                payload=cast(Mapping[str, JsonInput], _json_attributes(operation)),
            )
            return ()
        if opcode == "human.request":
            request_id = str(operation.op_id)
            log.append(
                "human.required",
                op_id=request_id,
                payload={"request": _attribute_string(operation, "request") or request_id},
            )
            if request_id not in human_approvals:
                raise HumanRequired(f"human approval required for {request_id}")
            return (Literal(True, BOOL_TYPE),) if operation.results else ()
        raise UnknownRuntimeOperation(f"unknown opcode reached runtime: {opcode}")

    def _semantic_literal(
        self,
        program: Program,
        operation: Operation,
        values: Mapping[ResultId, object],
    ) -> Literal:
        result_type = cast(TypeDescriptor, operation.results[0].type)
        operands = self._operands(operation, values)
        raw: object = operation.attribute("value")
        if raw is None and operands:
            raw = _json_value(operands[0])
        if raw is None:
            raw = _json_attributes(operation)
        return Literal(
            cast(JsonInput, raw),
            result_type,
            Provenance(
                produced_by=cast(ActorRef, program.actor),
                operation_id=cast(OpId, operation.op_id),
            ),
        )

    def _make_patch(
        self,
        program: Program,
        operation: Operation,
        values: Mapping[ResultId, object],
    ) -> Patch:
        target = _required_attr(operation, "target")
        base_version = operation.attribute("base_version")
        if not isinstance(base_version, (str, int)) or isinstance(base_version, bool):
            raise BackendFailure("state.patch requires base_version")
        write_set = _attribute_strings(operation, "write_set")
        writes = _attribute_object(operation, "writes")
        if not writes:
            path = _attribute_string(operation, "path")
            if path is None or not operation.operands:
                raise BackendFailure("state.patch requires writes or path plus one operand")
            writes = {path: _json_value(self._operands(operation, values)[0])}
        return Patch(
            patch_id=_attribute_string(operation, "patch_id") or f"patch.{operation.op_id}",
            target=target,
            base_version=base_version,
            writes=cast(Mapping[str, JsonInput], writes),
            declared_write_set=write_set,
            produced_by=cast(ActorRef, program.actor),
            provenance=Provenance(
                produced_by=cast(ActorRef, program.actor),
                operation_id=cast(OpId, operation.op_id),
                source_refs=_source_refs(operation),
            ),
        )

    @staticmethod
    def _validate_commit_contract(operation: Operation, patch: Patch) -> None:
        """Bind a runtime patch to the statically verified commit contract."""

        operation_target = StateRef.parse(_required_attr(operation, "target")).base
        patch_target = cast(StateRef, patch.target).base
        if patch_target != operation_target:
            raise WriteScopeError(
                f"patch target {patch_target} does not match operation target {operation_target}"
            )
        operation_scopes = tuple(
            normalize_write_scope(scope) for scope in _attribute_strings(operation, "write_set")
        )
        if not operation_scopes:
            raise WriteScopeError("state.commit requires a non-empty write_set")
        for path in patch.changed_paths:
            if not any(_runtime_path_allowed(path, scope) for scope in operation_scopes):
                raise WriteScopeError(
                    f"patch path {path!r} is outside operation write_set {operation_scopes!r}"
                )

    def _verified_value(self, program: Program, operation: Operation, source: object) -> Literal:
        result_type = cast(TypeDescriptor, operation.results[0].type)
        if not isinstance(source, Literal):
            source_value = cast(JsonInput, _json_value(source))
            previous = Provenance()
        else:
            source_value = cast(JsonInput, source.value)
            previous = source.provenance or Provenance()
        refs = previous.source_refs + _source_refs(operation)
        provenance = Provenance(
            source_refs=refs,
            produced_by=cast(ActorRef, program.actor),
            operation_id=cast(OpId, operation.op_id),
            timestamp=previous.timestamp,
            evidence_refs=previous.evidence_refs,
            confidence=previous.confidence,
        )
        return Literal(source_value, result_type, provenance)

    def _coerce_backend_value(
        self,
        response: object,
        operation: Operation,
        *,
        result_type: TypeDescriptor | None = None,
    ) -> Literal:
        result_type = result_type or cast(TypeDescriptor, operation.results[0].type)
        if isinstance(response, Literal):
            if response.type is not None and response.type != result_type:
                raise BackendFailure(
                    f"backend result type mismatch for {operation.op_id}: "
                    f"expected {result_type}, got {response.type}"
                )
            return Literal(
                cast(JsonInput, response.value),
                response.type or result_type,
                response.provenance,
            )
        return Literal(cast(JsonInput, response), result_type)

    @staticmethod
    def _operands(operation: Operation, values: Mapping[ResultId, object]) -> tuple[object, ...]:
        resolved: list[object] = []
        for operand in operation.operands:
            if isinstance(operand, ValueRef):
                try:
                    resolved.append(values[operand.id])
                except KeyError as exc:
                    raise BackendFailure(f"unresolved runtime reference: {operand.id}") from exc
            else:
                resolved.append(operand)
        return tuple(resolved)

    @staticmethod
    def _require_value(
        operation: Operation,
        values: Mapping[ResultId, object],
        index: int,
        expected_type: type[object],
    ) -> object:
        operands = Runtime._operands(operation, values)
        if len(operands) <= index or not isinstance(operands[index], expected_type):
            raise BackendFailure(
                f"{operation.opcode} operand {index} must be {expected_type.__name__}"
            )
        return operands[index]


JSON_TYPE = TypeDescriptor.from_text("Json")
BOOL_TYPE = TypeDescriptor.from_text("Bool")


def _required_attr(operation: Operation, name: str) -> str:
    value = _attribute_string(operation, name)
    if value is None:
        raise BackendFailure(f"{operation.opcode} requires attribute {name}")
    return value


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


def _json_attributes(operation: Operation) -> dict[str, object]:
    return cast(
        dict[str, object],
        thaw_json(cast(FrozenDict[str, JsonValue], operation.attributes)),
    )


def _source_refs(operation: Operation) -> tuple[ValueRef, ...]:
    return tuple(operand for operand in operation.operands if isinstance(operand, ValueRef))


def _json_value(value: object) -> object:
    if isinstance(value, Literal):
        return thaw_json(cast(JsonValue, value.value))
    if isinstance(value, StateObject):
        return value.json_value()
    if isinstance(value, StateProjection):
        return value.json_value()
    if isinstance(value, Patch):
        return {"target": str(value.target), "base_version": value.base_version}
    return value


def _diff_values(left: object, right: object) -> dict[str, object]:
    return {"equal": left == right, "left": left, "right": right}


def _runtime_path_allowed(path: str, scope: str) -> bool:
    return path == scope or (scope.endswith(".*") and path.startswith(scope[:-2] + "."))


def _runtime_error_code(error: RuntimeErrorBase) -> str:
    if isinstance(error, AssertionFailure):
        return "AIR012"
    if isinstance(error, HumanRequired):
        return "AIR014"
    if isinstance(error, UnknownRuntimeOperation):
        return "AIR002"
    return "AIR013"


def _state_error_code(error: StateError) -> str:
    if isinstance(error, StaleVersionError):
        return "AIR011"
    if isinstance(error, WriteScopeError):
        return "AIR010"
    if isinstance(error, (InvalidPatchError, PatchIntegrityError)):
        return "AIR010"
    return "AIR009"
