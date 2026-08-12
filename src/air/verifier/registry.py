"""Core opcode registry used by the AIR verifier and runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpcodeSpec:
    """Static shape metadata for one known AIR opcode."""

    name: str
    min_results: int
    max_results: int
    min_operands: int = 0
    max_operands: int | None = None

    def accepts_result_count(self, count: int) -> bool:
        return self.min_results <= count <= self.max_results

    def accepts_operand_count(self, count: int) -> bool:
        return count >= self.min_operands and (
            self.max_operands is None or count <= self.max_operands
        )


CORE_OPCODE_SPECS: tuple[OpcodeSpec, ...] = (
    OpcodeSpec("core.fact", 1, 1, 0, 1),
    OpcodeSpec("core.claim", 1, 1, 0, 1),
    OpcodeSpec("core.goal", 1, 1, 0, 1),
    OpcodeSpec("core.constraint", 1, 1, 0, 1),
    OpcodeSpec("state.read", 1, 1),
    OpcodeSpec("state.project", 1, 1),
    OpcodeSpec("state.diff", 1, 1, 2, 2),
    OpcodeSpec("state.patch", 1, 1, 0, 1),
    OpcodeSpec("state.commit", 0, 1, 1, 1),
    OpcodeSpec("agent.invoke", 1, 1, 0, 1),
    OpcodeSpec("agent.spawn", 1, 1, 0, 1),
    OpcodeSpec("agent.await", 1, 1, 1, 1),
    OpcodeSpec("agent.join", 1, 1, 1),
    OpcodeSpec("tool.call", 1, 1, 0, 1),
    OpcodeSpec("verify.check", 1, 1, 1, 1),
    OpcodeSpec("verify.assert", 0, 0, 1, 1),
    OpcodeSpec("human.notify", 0, 0),
    OpcodeSpec("human.request", 0, 1, 0, 0),
)


class OpcodeRegistry:
    """Explicit registry; lookup failure is intentionally fail-closed."""

    def __init__(self, specs: tuple[OpcodeSpec, ...] = CORE_OPCODE_SPECS) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def get(self, opcode: str) -> OpcodeSpec | None:
        return self._specs.get(opcode)

    def register(self, spec: OpcodeSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"opcode already registered: {spec.name}")
        self._specs[spec.name] = spec

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._specs)
