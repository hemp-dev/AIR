# AIR v0.1 deterministic benchmark harness

The benchmark tests a falsifiable question: when several agents share a
semantic task, which improvements come from structured representation, which
come from shared state, and which are attributable to AIR's verifier/runtime?
AIR is allowed to lose. The harness therefore reports `NL -> JSON`,
`JSON -> SJSON`, and `SJSON -> AIR` separately; it never publishes one
undifferentiated “AIR saved X%” number.

## Reproduce the smoke run

The suite is offline and uses deterministic fixtures plus mock agents. From a
fresh checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m air.bench --suite smoke --variants NL,JSON,SJSON,AIR \
  --output artifacts/smoke.json
python -m air.bench --suite smoke --variants NL,JSON,SJSON,AIR \
  --format markdown
```

The JSON output contains raw per-run records and the aggregate report. The
Markdown form is an operator-friendly summary. `--scenario` accepts an exact
scenario name or a family prefix, `--repeats` repeats a deterministic fixture,
and `--seed` selects the fixture seed.

## Four comparable modes

- `NL` sends human-readable messages with relevant context included.
- `JSON` sends structured full-payload messages without shared-state
  projection.
- `SJSON` uses the real immutable `StateStore`, references, projections and
  patches, but keeps coordination messages as ordinary JSON. It is the strong
  shared-state control baseline.
- `AIR` uses the same state semantics and fixtures as `SJSON`, then executes a
  canonical AIR `Program` through the verifier and runtime. AIR-Text and
  optimizer passes are not part of this baseline.

Every mode is run against one `ScenarioCase` contract: logical input,
expected output, allowed effects and required provenance. The runner's
semantic-equivalence gate rejects a multi-mode run if any actual result differs
from the fixture's expected result.

## Scenarios

The smoke suite includes:

- information relay (`secret_number=713`, expected transform `2140`);
- long-context projection with a deterministic approximately 10 KB context;
- four-worker fan-out and join;
- shared editing with disjoint and overlapping stale patches;
- external-untrusted prompt-injection-like data and a forbidden write;
- operator audit with a rejected candidate, retry, provenance and two commits.

The shared-edit family also exposes an unrecoverable stale case in the full
suite selection. All scenarios use deterministic values and no network/API
credentials.

## Accounting rules

The communication ledger records sender, receiver, kind, logical content ID and
exact UTF-8 `payload_size_bytes`. The context-materialization ledger records
which consumer loaded which reference, why, exact bytes and optional tokens.
Transport and inference context are intentionally separate:

```text
coordination_bytes       = serialized transport payloads
materialized_context_bytes = payloads entering an agent context
source_context_bytes     = authoritative fixture size
artifact_bytes            = serialized AIR/control artifacts, when applicable
```

A reference does not charge the referenced object as transport. If a projection
is loaded into a consumer context, those projection bytes are charged. This is
why `SJSON`/`AIR` can have small coordination messages and still show a
non-zero materialized context.

Byte serialization is canonical and stable. Token counts are nullable: the
offline run does not install a model tokenizer, so `input_tokens`,
`output_tokens` and other model-usage fields remain `null`. The harness never
derives token counts from characters or bytes. An exact counter can be injected
through `FunctionTokenCounter` or another `TokenCounter` implementation.

Mock timing is collected with a monotonic high-resolution clock for
instrumentation only. It is not evidence of provider latency or model cost.

## First deterministic smoke observations

These byte values are from the reproducible fixture payloads; timing is omitted
because it is machine-dependent.

| Scenario | Mode | Coordination bytes | Materialized bytes | Conflicts | Unauthorized executions |
|---|---:|---:|---:|---:|---:|
| information-relay | NL | 65 | 65 | 0 | 0 |
| information-relay | JSON | 41 | 41 | 0 | 0 |
| information-relay | SJSON | 63 | 21 | 0 | 0 |
| information-relay | AIR | 87 | 21 | 0 | 0 |
| long-context.small | NL | 10,285 | 10,285 | 0 | 0 |
| long-context.small | JSON | 10,318 | 10,318 | 0 | 0 |
| long-context.small | SJSON | 107 | 65 | 0 | 0 |
| long-context.small | AIR | 132 | 65 | 0 | 0 |
| fanout-join | JSON | 894 | 894 | 0 | 0 |
| fanout-join | SJSON | 386 | 226 | 0 | 0 |
| fanout-join | AIR | 478 | 226 | 0 | 0 |
| shared-edit.conflict | SJSON | 112 | 20 | 1 | 0 |
| shared-edit.conflict | AIR | 158 | 20 | 1 | 0 |
| security-taint | SJSON | 74 | 90 | 0 | 0 |
| security-taint | AIR | 74 | 90 | 0 | 0 |
| operator-audit | SJSON | 55 | 46 | 0 | 0 |
| operator-audit | AIR | 55 | 46 | 0 | 0 |

The initial result is intentionally mixed:

- structured JSON is smaller than NL in some small message fixtures;
- `JSON -> SJSON` produces the large context/materialization reduction in the
  long-context, fan-out and audit cases;
- `SJSON -> AIR` keeps shared-state materialization equal in these fixtures but
  adds verifier/runtime operation and representation overhead on small tasks;
- AIR supplies fail-closed verification and an append-only event trail, while
  the security scenario still reports zero unauthorized executions across all
  modes;
- no custom AIR syntax or AIR+OPT claim is made by this run.

These are engineering observations from deterministic mocks, not LLM or
statistical claims. A negative AIR incremental result is a valid outcome under
ADR-010.

## Limitations and next experiment

This phase cannot establish provider latency, tokenizer behavior, model
reliability, prompt-injection susceptibility, or production concurrency. It
does establish the state/communication accounting boundary, deterministic
semantic equivalence, stale-write detection and verifier side-effect
containment.

The next minimal experiment is tokenizer-only: serialize the same logical
coordination actions for selected model tokenizers, include any repeated
schema/instruction overhead, and keep token fields marked exact only when the
tokenizer reports an exact count. Provider-backed semantic compilation should
follow only after the deterministic baseline is committed.

## Real-model Phase 2

The opt-in real-model extension is documented in
[`LIVE_BENCHMARKING.md`](LIVE_BENCHMARKING.md). It adds one provider-neutral
adapter boundary, paired randomized repetitions, provider-reported usage,
separate communication/inference ledgers and four high-information scenarios.
The deterministic suite remains the offline semantic control and is unchanged
by live execution.
