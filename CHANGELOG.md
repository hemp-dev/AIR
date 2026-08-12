# Changelog

All notable changes to AIR are documented here.

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
