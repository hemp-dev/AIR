# AIR v0.1 real-model benchmark (Phase 2)

The real-model benchmark is an opt-in extension of the deterministic AIR
harness. It measures provider-reported inference usage while preserving the
offline benchmark as the semantic control. The live path is never used by
ordinary `pytest` or by the default offline CLI.

## Provider boundary

Phase 2 contains one real provider adapter: the standard-library OpenAI
Responses transport. It is isolated behind `ModelAdapter.invoke(request)` and
normalizes the provider response into `ModelResponse`. The adapter records
provider-reported `input_tokens`, `output_tokens`, cached input tokens and
reasoning tokens when present; unavailable fields remain `null`. It never
estimates tokens from characters or bytes.

Credentials are read from `OPENAI_API_KEY` only. The key is sent in the HTTP
header and is not included in request records, fixture records, reports or
error messages. The model is supplied by `--model` or `AIR_BENCH_MODEL`.
There is no provider dependency in AIR Core.

## Explicit execution

The live subcommand requires `--execute` as an acknowledgement that it can
make network calls and incur provider charges. Without a key, it fails before
the first request. Unit tests inject a fake `ModelAdapter` or HTTP transport;
they never contact a provider and do not fabricate live results.

A small long-context run can be reproduced with:

```bash
export OPENAI_API_KEY='...'
export AIR_BENCH_MODEL='gpt-4o-mini'

python -m air.bench live \
  --execute \
  --scenario long-context \
  --model "$AIR_BENCH_MODEL" \
  --variants NL,JSON,SJSON,AIR \
  --context-sizes small \
  --repetitions 1 \
  --warmup-runs 0 \
  --output artifacts/live-long-context.json

python -m air.bench live \
  --execute \
  --scenario long-context \
  --model "$AIR_BENCH_MODEL" \
  --variants NL,JSON,SJSON,AIR \
  --context-sizes small \
  --repetitions 1 \
  --format markdown \
  --output artifacts/live-long-context.md
```

The recommended measurement profile uses at least five repetitions and more
than one scale. For the four Phase 2 scenarios, the configurable parameters
are:

```bash
python -m air.bench live --help

# Example configuration for a small research run:
python -m air.bench live \
  --execute \
  --scenario long-context \
  --model "$AIR_BENCH_MODEL" \
  --context-sizes small,medium,large \
  --repetitions 5 \
  --warmup-runs 1 \
  --timeout 60 \
  --retries 1 \
  --output artifacts/live-long-context.json
```

The CLI supports `long-context`, `relay`, `fanout` and `adversarial-trust`.
Use `--relay-depths 2,4,8` and `--fanout-widths 2,4,8` to request the full
depth/width series. Optional price-card arguments stamp an external pricing
profile onto the result; raw token usage remains independent of prices.

## Paired design and ledgers

Each fixture is generated once and reused for `NL`, `JSON`, `SJSON` and `AIR`.
Its canonical semantic identity is hashed into `fixture_id`, so repetitions
and modes can be paired without persisting prompt content in call records.
Mode order is deterministically shuffled from the fixture ID, repetition and
seed. The actual order is recorded. Warmups run through the same mode path but
have negative internal repetition IDs and are excluded from result aggregates.

Every model invocation appends a `LiveCallRecord`. The record includes the
run/scenario/mode/agent identity, request and context byte counts, normalized
usage, timing, retry count, success and request/output hashes. It does not
store credentials or prompt/output text by default.

Two costs remain separate:

```text
communication_bytes       serialized coordination payload
materialized_context_bytes serialized messages entering the model invocation
```

A shared-state reference can therefore be cheap to coordinate while its
projection can still be expensive in inference context. `request_bytes` is
also retained as the canonical provider-neutral request-envelope size. AIR
artifact bytes and verifier time are recorded separately from model time.

Reports expose raw per-call records, per-agent aggregates, per-scenario-run
totals and per-mode statistics. Numeric aggregates contain count, mean,
median, minimum, maximum, sample standard deviation and p95 when a metric is
available. Nullable provider fields stay unavailable rather than being
replaced by estimates.

## Scenarios

- **Long context scaling:** deterministic `small`, `medium`, `large` and
  `very_large` source contexts contain a small relevant projection. The report
  includes the actual source byte size, materialized context, provider usage,
  preprocessing, provider and wall time.
- **Relay depth:** depths 2, 4 and 8 pass a fact through causally necessary
  intermediate outputs. The final agent cannot access the original fixture
  directly.
- **Fan-out/join width:** widths 2, 4 and 8 give workers a common base and a
  distinct task, then charge a separate join call. Calls are sequential; no
  parallel latency claim is made.
- **Adversarial trust:** an untrusted external field contains an instruction-
  like request to approve a transaction. The model may propose an action, but
  AIR's protected effect is a mock and the verifier/runtime must keep
  `unauthorized_executions == 0`.

The Markdown report separates `NL -> JSON`, `JSON -> SJSON` and `SJSON -> AIR`
deltas. It also emits machine-readable scale series for dotted scenario
families such as `long-context.medium`, `relay.depth8` and `fanout.width4`.
No combined `NL -> AIR` claim is used as the primary attribution.

## Measurement limitations

The first adapter does not stream responses, so time-to-first-token is
`null`. Provider-side caching, queueing, service load and rate limits are not
fully controllable; cached-token fields are reported when the provider sends
them. The experiment covers one provider/model configuration and synthetic
fixtures, so it cannot establish behavior for all models or production
workloads. The current runner executes workflow calls sequentially. Prices are
optional context, not a basis for conclusions.

No provider-backed run was made while implementing this phase. The commands
above are the exact maintainer-controlled reproduction path; live output must
only be reported when it was actually produced by the configured provider.
