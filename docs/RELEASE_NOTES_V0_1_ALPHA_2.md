# AIR v0.1.0-alpha.2

Release date: 2026-08-12

This release adds the deterministic executable AIR core on top of the
canonical model from `v0.1.0-alpha.1`.

## Included

- immutable normalized state refs, snapshots, projections and patches;
- optimistic version checks, write scopes, commit history and replay integrity;
- fail-closed static verifier with structured diagnostics;
- effect/capability, trust-flow and high-risk authorization checks;
- sequential runtime for the v0.1 core operation set;
- deterministic mock agent/tool boundaries and completed-future semantics;
- append-only event log and operator projection;
- adversarial, state, verifier and end-to-end tests.

## Explicitly deferred

AIR-Text, benchmark variants, persistent/distributed storage, provider-backed
LLM execution, MCP/A2A adapters, UI and irreversible real-world tools remain
out of scope.
