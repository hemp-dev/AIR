# AIR v0.1.0-alpha.1 Release Notes

**Release date:** 2026-08-12  
**Release type:** foundation pre-release  
**Implemented scope:** Milestone 0 and Milestone 1 (`T00`–`T04`)

## Summary

This release establishes the canonical AIR data model. It deliberately stops before textual parsing, verification, state mutation and runtime execution so that later milestones can build on a stable, testable semantic foundation.

## Included

- project packaging and developer checks in `pyproject.toml`;
- validated immutable `ProgramId`, `OpId`, `ResultId`, `ActorRef` and `ValueRef` objects;
- primitive, container, semantic and runtime `TypeDescriptor` implementations;
- immutable JSON-compatible literals, arrays and objects;
- `TrustLabel` with explicit, non-ranking trust transitions;
- immutable `Provenance` with source refs, actor, operation, timestamp and evidence refs;
- `Effect`, `CapabilityRule` and `CapabilitySet` with exact, segment and glob matching;
- immutable `Operation`, `ResultDecl` and `Program` containers;
- duplicate operation and SSA result checks at model construction time;
- strict deterministic AIR-JSON serialization/deserialization;
- rejection of malformed identifiers, unsupported types/effects, duplicate JSON keys and unknown fields;
- 24 passing tests.

## Validation

The release was checked with:

```text
python -m pytest -q       # 24 passed
ruff check .              # passed
ruff format --check .     # passed
python -m mypy src        # passed
```

The exact serialized AIR-JSON representation uses stable key ordering and compact separators. UTF-8 bytes can therefore be measured reproducibly in later benchmark work.

## Explicit limitations

This is not the complete AIR v0.1 MVP. The following are intentionally deferred:

- AIR-Text frontend;
- opcode registry and static verifier;
- capability enforcement during execution;
- immutable/versioned `StateStore`;
- patches, optimistic commits and replay behavior;
- runtime scheduler and mock agent/tool backends;
- event log and operator projection;
- `NL`, `JSON`, `SJSON`, `AIR` benchmark harness;
- provider-backed LLMs, MCP/A2A adapters, databases and UI.

## Next milestone

The next release should implement `T10`–`T12`: a non-executing AIR-Text lexer/parser/printer that remains a frontend to the canonical model.
