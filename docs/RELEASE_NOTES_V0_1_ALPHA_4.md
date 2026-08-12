# AIR v0.1.0-alpha.4

## Scope

This release adds the opt-in real-model benchmark Phase 2 on top of the
deterministic executable AIR core and offline benchmark harness. The live
layer is measurement infrastructure, not a change to AIR semantics or a
claim that AIR must use fewer tokens than SJSON.

## Added

- provider-neutral `ModelAdapter` / `ModelRequest` / `ModelResponse` models;
- one standard-library OpenAI Responses adapter with environment credentials,
  configurable model, timeout and explicit retry behavior;
- exact normalized provider usage fields, raw provider usage metadata when
  available, nullable unavailable fields and optional external pricing;
- serializable experiment profiles with repetitions, warmups, seeded
  randomized mode order and fixture identity hashes;
- separate communication and materialized inference-context accounting;
- per-call `LiveCallRecord`, per-agent attribution and cumulative
  per-scenario/per-mode metrics;
- long-context scaling, relay depth, fan-out/join width and adversarial-trust
  scenarios;
- machine-readable JSON aggregates/scale series and neutral Markdown reports;
- offline fake-adapter, mocked-transport, serialization, statistics, security
  and CLI safety tests.

## Safety and reproducibility

Live execution requires `python -m air.bench live --execute` and
`OPENAI_API_KEY`. Normal `pytest`, the deterministic benchmark and CI do not
make network calls. Call records contain IDs, hashes and measurements, not
credentials or prompt/output text by default. Warmups are excluded from
aggregates, execution order is recorded, and provider token fields are never
estimated.

## Validation

- 73 tests pass;
- Ruff and mypy pass;
- `compileall` passes;
- the full deterministic `NL`/`JSON`/`SJSON`/`AIR` benchmark passes with 32
  successful results.

No real provider call was made while preparing this release. See
[`LIVE_BENCHMARKING.md`](LIVE_BENCHMARKING.md) for the maintainer-controlled
reproduction command and measurement limitations.
