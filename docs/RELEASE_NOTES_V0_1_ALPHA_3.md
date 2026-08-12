# AIR v0.1.0-alpha.3

## Scope

This release adds the offline AIR Benchmark Harness v0.1 on top of the
deterministic executable AIR core.

## Added

- four comparable modes: `NL`, `JSON`, `SJSON` and `AIR`;
- deterministic information-relay, long-context, fan-out/join, shared-edit,
  security/taint and operator-audit fixtures;
- representation-independent communication and context-materialization
  ledgers;
- exact canonical UTF-8 byte accounting and nullable exact-token fields;
- pluggable `TokenCounter` boundary with a no-op offline implementation;
- semantic-equivalence gate across deterministic modes;
- raw JSON and aggregate Markdown/JSON reporting;
- offline CLI:

  ```bash
  python -m air.bench --suite smoke --variants NL,JSON,SJSON,AIR \
    --output artifacts/smoke.json
  ```

- benchmark documentation and deterministic harness tests.

## First observations

The smoke fixtures show substantial `JSON -> SJSON` context reduction on
long-context, fan-out and audit cases. In these small fixtures `SJSON -> AIR`
keeps materialized context equal but adds canonical-operation and verifier
overhead. All four modes are semantically equivalent, shared-edit conflicts
are detected, and unauthorized executions remain zero. Exact model token
counts and provider latency are intentionally unavailable until a later
tokenizer/provider phase.

## Out of scope

AIR-Text, AIR+OPT, MCP/A2A adapters, persistent/distributed storage, UI and
provider-backed LLM execution remain out of scope.
