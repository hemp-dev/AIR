# Changelog

All notable changes to AIR are documented here.

## [0.1.0-alpha.4] — 2026-08-12

Opt-in real-model benchmark Phase 2 for AIR v0.1.

### Added

- provider-neutral `ModelAdapter`, normalized `ModelResponse` and one
  standard-library OpenAI Responses adapter;
- explicit `--execute` live CLI with environment-only credentials, model,
  timeout, retry, repetition, warmup and pricing configuration;
- paired, seeded mode ordering and fixture hashing across NL, JSON, SJSON and
  AIR;
- separate communication and inference-context ledgers plus per-call and
  per-agent attribution;
- long-context, relay-depth, fan-out/join and adversarial-trust live scenarios;
- provider usage normalization, nullable metrics, statistics, deltas, scale
  series and JSON/Markdown reports;
- offline fake-adapter and mocked-transport tests; no live provider results
  are included in this release.

### Not included yet

- AIR-Text parser/printer;
- additional real provider adapters or streaming time-to-first-token;
- provider-controlled caching isolation, concurrency experiments, persistence,
  UI, MCP/A2A integrations or AIR+OPT.

## [0.1.0-alpha.2] — 2026-08-12

Deterministic executable-core release for Agent IR v0.1.

### Added

- normalized state references and immutable versioned `StateStore` snapshots;
- projected reads with materialized-byte accounting;
- validated patches, write scopes, optimistic concurrency and idempotent replay;
- fail-closed core opcode registry and structured verifier diagnostics;
- static checks for SSA references, operation shapes, types, effects, capabilities, trust transitions and risk authorization;
- sequential runtime dispatch for state, semantic, verification, human, agent and tool operations;
- sequential `agent.spawn`/`agent.await`/`agent.join` future semantics;
- deterministic mock agent/tool executors;
- append-only runtime events and deterministic operator projection;
- end-to-end and adversarial security tests.

### Not included yet

- AIR-Text parser/printer;
- provider-backed, MCP/A2A, network or persistent-storage integrations;
- benchmark variants and CLI.

## [0.1.0-alpha.1] — 2026-08-12

Initial foundation release for Agent IR v0.1.

### Added

- Python 3.12+ package and development configuration;
- immutable validated AIR identifiers and SSA references;
- primitive, container, semantic and runtime type descriptors;
- immutable JSON-compatible literals and nested values;
- trust labels, explicit trust transition checks and provenance metadata;
- effect and capability data structures with deny-overrides-allow matching;
- immutable `Operation`, `ResultDecl` and `Program` model;
- deterministic AIR-JSON serializer/deserializer;
- validation tests for IDs, types, trust, effects, duplicate IDs and round-trips.

### Not included yet

- AIR-Text parser/printer;
- deterministic verifier and opcode registry;
- StateStore and patch commits;
- runtime, backends and event projection;
- benchmark variants and CLI.
