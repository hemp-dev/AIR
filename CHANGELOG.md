# Changelog

All notable changes to AIR are documented here.

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
