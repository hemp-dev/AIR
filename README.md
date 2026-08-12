# AIR — Agent IR v0.1

AIR (Agent Intermediate Representation) is a small research runtime for coordinating LLM agents through typed operations and shared semantic state instead of repeated natural-language context transfer.

> Research status: `v0.1.0-alpha.1` implements Milestone 0–1 — the canonical AIR model and deterministic AIR-JSON serialization. The parser, verifier, state store, runtime and benchmark harness are planned next.

## Why AIR

The project tests three related hypotheses:

1. Shared state, immutable objects, projections and patches reduce repeated coordination context.
2. A typed IR adds value beyond shared-state JSON through explicit operations, effects, capabilities and deterministic verification.
3. A runtime can reduce unnecessary model-mediated coordination while improving auditability and reliability.

The experiment is designed to compare four fair variants: `NL`, `JSON`, `SJSON` and `AIR`. A negative result is valid: if custom AIR syntax does not improve on structured JSON, the typed runtime can remain while JSON becomes the model-facing representation.

## Current release

`v0.1.0-alpha.1` contains:

- Python 3.12+ package scaffold;
- immutable validated identifiers and SSA references;
- primitive, container, semantic and runtime type descriptors;
- immutable JSON-compatible literals and nested values;
- trust labels, explicit trust transitions and provenance metadata;
- effects and capability rules with deny-overrides-allow matching;
- immutable `Operation`, `ResultDecl` and `Program` objects;
- duplicate operation/result detection;
- deterministic canonical AIR-JSON serialization and deserialization;
- 24 unit and integration tests for the foundation model.

This release does not execute programs. AIR-Text, verification, state mutation, backends, event projection and benchmarks are not part of this alpha.

## Quick start

Create an isolated development environment and install the package with its validation tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run the foundation checks:

```bash
python -m pytest -q
ruff check .
ruff format --check .
python -m mypy src
```

## Minimal example

The canonical in-memory model is authoritative; JSON is only its deterministic interchange representation.

```python
from air.ir import Literal, Operation, Program, ResultDecl, serialize_program

program = Program(
    program_id="prog.demo",
    actor="agent://planner",
    operations=(
        Operation(
            op_id="op1",
            opcode="core.fact",
            results=(ResultDecl("%fact", "Fact<Int,UserSupplied>"),),
            operands=(Literal(713, "Int"),),
        ),
    ),
)

print(serialize_program(program))
```

## Repository map

- [`src/air/ir`](src/air/ir) — canonical AIR data model and AIR-JSON serde;
- [`tests`](tests) — foundation tests;
- [`docs/AIR_SPEC_V0_1.md`](docs/AIR_SPEC_V0_1.md) — normative model and operation specification;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — component boundaries and lifecycle;
- [`docs/SECURITY_AND_VERIFICATION.md`](docs/SECURITY_AND_VERIFICATION.md) — threat model and fail-closed rules;
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — milestone plan;
- [`docs/CODEX_TASKS.md`](docs/CODEX_TASKS.md) — ordered implementation queue;
- [`docs/BENCHMARK_PROTOCOL.md`](docs/BENCHMARK_PROTOCOL.md) — experimental protocol;
- [`docs/RELEASE_NOTES_V0_1_ALPHA_1.md`](docs/RELEASE_NOTES_V0_1_ALPHA_1.md) — release scope and known gaps.

## Design invariants

- The canonical representation is a typed data model, not AIR-Text.
- State and coordination messages remain separate.
- Semantic objects are immutable; updates will create new versions.
- State writes will go through validated patches and commits.
- Unknown operations and effects fail closed.
- Effects must be allowed by actor capabilities.
- `ExternalUntrusted` cannot implicitly become `Verified`.
- Deterministic code verifies and executes LLM proposals.
- Operator text is a projection of structured events and state.

## Roadmap

Implementation follows [`docs/CODEX_TASKS.md`](docs/CODEX_TASKS.md):

1. AIR-Text lexer, parser and printer;
2. deterministic opcode registry and verifier;
3. immutable/versioned shared state store;
4. runtime and deterministic mock backends;
5. event-driven operator projection;
6. offline `NL`/`JSON`/`SJSON`/`AIR` benchmark harness;
7. deterministic benchmark scenarios and optional optimizations.

Provider-backed LLMs, MCP/A2A adapters, production persistence, UI and irreversible real-world tools remain out of scope for the MVP foundation.

## License

No license has been selected for this research repository yet. Until one is added, the source should not be assumed to be available for redistribution or production use.
