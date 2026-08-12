# AIR — Agent IR v0.1

AIR (Agent Intermediate Representation) is a small research runtime for coordinating LLM agents through typed operations and shared semantic state instead of repeated natural-language context transfer.

> Research status: `v0.1.0-alpha.4` adds an explicitly opt-in real-model benchmark layer while keeping the deterministic harness as the offline semantic control. AIR-Text remains a separate follow-up milestone.

## Why AIR

The project tests three related hypotheses:

1. Shared state, immutable objects, projections and patches reduce repeated coordination context.
2. A typed IR adds value beyond shared-state JSON through explicit operations, effects, capabilities and deterministic verification.
3. A runtime can reduce unnecessary model-mediated coordination while improving auditability and reliability.

The experiment is designed to compare four fair variants: `NL`, `JSON`, `SJSON` and `AIR`. A negative result is valid: if custom AIR syntax does not improve on structured JSON, the typed runtime can remain while JSON becomes the model-facing representation.

## Current release

`v0.1.0-alpha.4` contains:

- Python 3.12+ package scaffold;
- immutable validated identifiers and SSA references;
- primitive, container, semantic and runtime type descriptors;
- immutable JSON-compatible literals and nested values;
- trust labels, explicit trust transitions and provenance metadata;
- effects and capability rules with deny-overrides-allow matching;
- immutable `Operation`, `ResultDecl` and `Program` objects;
- duplicate operation/result detection;
- deterministic canonical AIR-JSON serialization and deserialization;
- normalized `wm://` state references and immutable versioned `StateStore` snapshots;
- validated patches with declared write sets, optimistic concurrency and idempotent replay;
- a fail-closed opcode registry and structured verifier diagnostics for SSA, types, effects, capabilities, trust and HITL risk;
- sequential runtime execution for the core operation set, including mock agent/tool boundaries and `spawn`/`await`/`join` futures;
- append-only structured events and deterministic operator-facing projections;
- offline `NL`/`JSON`/`SJSON`/`AIR` benchmark modes with exact byte/context accounting, nullable token fields, deterministic scenarios, semantic-equivalence gating and JSON/Markdown reports;
- opt-in real-model benchmark Phase 2 with one OpenAI Responses adapter, provider-reported usage normalization, paired randomized repetitions, warmups, per-call/per-agent ledgers, four scalable scenarios and JSON/Markdown reports;
- deterministic unit, integration and adversarial tests for the model and executable core.

This release does not include an AIR-Text parser/printer, additional provider adapters, production persistence, UI or AIR+OPT passes. Live calls remain explicitly opt-in and are not part of the default test or benchmark paths.

## Quick start

Create an isolated development environment and install the package with its validation tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run the validation suite:

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
- [`src/air/verifier`](src/air/verifier) — deterministic registry and static verification;
- [`src/air/state`](src/air/state) — immutable snapshots, projections and patch commits;
- [`src/air/runtime`](src/air/runtime) — verified sequential execution and event collection;
- [`src/air/backends`](src/air/backends) — provider-independent deterministic mock boundaries;
- [`src/air/bench`](src/air/bench) — deterministic benchmark modes, scenarios, ledgers, metrics and reports;
- [`src/air/projection`](src/air/projection) — operator projection from structured events;
- [`tests`](tests) — model, security, state and end-to-end tests;
- [`docs/EXECUTABLE_CORE.md`](docs/EXECUTABLE_CORE.md) — executable-core lifecycle and API contract;
- [`docs/AIR_SPEC_V0_1.md`](docs/AIR_SPEC_V0_1.md) — normative model and operation specification;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — component boundaries and lifecycle;
- [`docs/SECURITY_AND_VERIFICATION.md`](docs/SECURITY_AND_VERIFICATION.md) — threat model and fail-closed rules;
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — milestone plan;
- [`docs/CODEX_TASKS.md`](docs/CODEX_TASKS.md) — ordered implementation queue;
- [`docs/BENCHMARK_PROTOCOL.md`](docs/BENCHMARK_PROTOCOL.md) — experimental protocol;
- [`docs/BENCHMARKING.md`](docs/BENCHMARKING.md) — harness usage, accounting rules and first deterministic observations;
- [`docs/LIVE_BENCHMARKING.md`](docs/LIVE_BENCHMARKING.md) — opt-in real-model Phase 2 usage and measurement limits;
- [`docs/RELEASE_NOTES_V0_1_ALPHA_4.md`](docs/RELEASE_NOTES_V0_1_ALPHA_4.md) — current release scope and known gaps;
- [`docs/RELEASE_NOTES_V0_1_ALPHA_1.md`](docs/RELEASE_NOTES_V0_1_ALPHA_1.md) — release scope and known gaps.

## Design invariants

- The canonical representation is a typed data model, not AIR-Text.
- State and coordination messages remain separate.
- Semantic objects are immutable; updates create new versions.
- State writes go through validated patches and commits.
- Unknown operations and effects fail closed.
- Effects must be allowed by actor capabilities.
- `ExternalUntrusted` cannot implicitly become `Verified`.
- Deterministic code verifies and executes LLM proposals.
- Operator text is a projection of structured events and state.

## Roadmap

Implementation follows [`docs/CODEX_TASKS.md`](docs/CODEX_TASKS.md):

1. AIR-Text lexer, parser and printer;
2. provider-backed/tokenizer benchmark experiments;
3. deterministic AIR+OPT experiments.

Provider-backed LLMs, MCP/A2A adapters, production persistence, UI and irreversible real-world tools remain out of scope for the MVP foundation.

## License

No license has been selected for this research repository yet. Until one is added, the source should not be assumed to be available for redistribution or production use.
