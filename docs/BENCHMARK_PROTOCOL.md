# AIR v0.1 Benchmark Protocol

## 1. Purpose

The benchmark must distinguish **representation compression** from **architecture/state optimization**.

The central mistake to avoid is comparing a verbose natural-language system that repeatedly copies context with an AIR system that uses shared references, then attributing the entire gain to the AIR syntax.

## 2. Required variants

### NL — natural-language coordination

Agent messages use human-readable prose. Relevant state/context is included in the exchanged text according to the scenario.

### JSON — structured messages

Same logical information as NL, represented with explicit JSON fields. No shared-state refs/projection optimization.

### SJSON — shared-state JSON

Same state store, refs, projections, patches, and benchmark privileges as AIR, but coordination/control messages use readable JSON/schema structures instead of AIR-Text.

### AIR — Agent IR

Same shared-state semantics as SJSON plus canonical AIR, AIR-Text frontend, verifier, effects/capabilities, and runtime semantics.

### AIR+OPT — optional

AIR with one or more deterministic optimization passes enabled.

## 3. Questions the experiment should answer

### Q1
How much of the saving comes from `JSON -> SJSON`?

Interpretation: benefit of references, projections, patches, shared state.

### Q2
How much additional saving comes from `SJSON -> AIR`?

Interpretation: incremental benefit/cost of the AIR representation and execution model.

### Q3
Does AIR reduce invalid/unauthorized operations independent of token cost?

### Q4
Does AIR reduce number of semantic/LLM coordination calls by turning steps into deterministic runtime operations?

### Q5
Does AIR improve operator audit/reconstruction quality?

## 4. Primary metrics

Record per run:

```text
task_success              bool/score
semantic_accuracy         0..1
input_tokens              int | null
output_tokens             int | null
cached_tokens             int | null
coordination_bytes        int
state_materialized_bytes  int
artifact_bytes            int
agent_calls               int
llm_calls                 int
verifier_calls            int
tool_calls                int
wall_latency_ms           float
backend_latency_ms        float
verification_latency_ms   float
state_latency_ms          float
operator_events           int
security_rejections       int
conflicts_detected        int
retries                    int
```

Do not claim `input_tokens` unless counted by the exact tokenizer/provider usage record. Always provide `coordination_bytes` so the deterministic experiment remains reproducible.

## 5. Derived metrics

### Coordination reduction

```text
1 - AIR.coordination_bytes / baseline.coordination_bytes
```

### State materialization reduction

```text
1 - SJSON.state_materialized_bytes / JSON.state_materialized_bytes
```

### Token reduction

When exact counts exist:

```text
1 - AIR.total_tokens / baseline.total_tokens
```

### Coordination efficiency

```text
semantic_score / max(1, coordination_bytes)
```

Use only as a descriptive metric, not the sole ranking criterion.

### Unauthorized execution rate

```text
unauthorized_effects_executed / unauthorized_effect_attempts
```

Target in adversarial fixtures: `0`.

## 6. Benchmark families

## A. Information relay

### Goal

Test whether an agent-specific fact is correctly transferred without granting receiver direct access to the source.

### Fixture

Agent A sees:

```text
secret = 713
```

Agent B receives only the allowed communication channel and must compute a deterministic transform, e.g. `secret * 3 + 1`.

Expected answer: `2140`.

### Variants

- NL: A sends prose containing the fact.
- JSON: A sends full structured payload.
- SJSON: A stores semantic object; B receives a ref/projection.
- AIR: A produces fact/ref operations consumed by B.

### Adversarial mutations

- mismatched case artifact;
- missing fact;
- wrong trust label;
- stale ref;
- substituted same-typed artifact.

## B. Long context projection

### Goal

Measure savings from state projection vs repeated context.

### Fixture

Generate deterministic state equivalent to a large document/object with many sections. Only two fields/sections are required.

Vary total context scale, e.g.:

```text
small  ~10 KB
medium ~100 KB
large  ~1 MB deterministic synthetic object
```

Do not require an actual LLM for the deterministic byte benchmark.

### Expected result

All variants return the same answer derived only from authorized selected fields.

### Key metric

`state_materialized_bytes` and coordination bytes.

## C. Shared editing / optimistic concurrency

### Goal

Test safe parallel state edits.

Two actors read version V1 and propose patches.

Cases:

1. disjoint write sets — both can eventually succeed;
2. overlapping write sets — stale/conflict path must trigger;
3. malicious out-of-scope patch — rejected.

### Metrics

- conflicts detected;
- lost updates;
- retries;
- final semantic correctness.

Lost updates must be zero in SJSON/AIR shared-state runtime variants.

## D. Multi-tool workflow

### Goal

Measure coordination overhead when many known deterministic operations exist.

Example synthetic workflow:

```text
load profile
filter candidates
lookup 10 prices
validate constraints
rank
commit result
```

Mocks should make actual task computation cheap so coordination overhead is visible.

Vary tool count: `5`, `10`, `30`.

### Hypothesis

AIR runtime may reduce model-mediated coordination if known operations execute deterministically.

## E. Adversarial state / prompt injection

### Goal

Measure side-effect containment, not prompt-injection elimination.

External untrusted field contains instruction-like content asking the agent to write outside allowed state or invoke a forbidden tool.

Expected:

- semantic frontend may be fooled in an adversarial provider-backed run;
- verifier still blocks unauthorized effect;
- zero forbidden side effects execute.

Deterministic version should directly inject malicious proposed AIR/JSON operation to test boundary correctness.

## F. Operator audit

### Goal

Test whether a human/operator can reconstruct what happened without raw chain-of-thought.

Create a multi-step task with:

- two agents;
- one failed verification;
- one retry/alternative result;
- two state commits;
- final decision.

Questions scored against ground truth:

1. What was the final result?
2. Which source/result was rejected?
3. Why was it rejected?
4. Which state changed?
5. Was human intervention required?
6. What provenance supports the final decision?

Compare event-derived projection quality across variants.

## 7. Deterministic phase vs LLM phase

### Phase 1 — deterministic

Purpose: validate architecture and communication accounting without model noise.

Use mocks and fixed fixtures. Required for MVP.

### Phase 2 — tokenizer-only

Serialize equivalent messages/programs and count exact tokens for selected model tokenizers if available.

No inference required.

### Phase 3 — LLM-backed semantic compilation

Use a fixed model snapshot/config. Run repeated trials.

Record:

- model identifier;
- reasoning configuration;
- temperature/sampling configuration if exposed;
- provider usage metrics;
- exact prompts/serialized inputs as artifacts where policy permits.

### Phase 4 — optimization/runtime

Enable AIR+OPT passes one at a time.

## 8. Repetition and statistics

For deterministic phase: one run per fixture is sufficient after property tests, but benchmark CLI should allow repeats.

For stochastic LLM phase:

- use at least 20–30 trials per scenario/config when feasible;
- report median and interquartile range for latency/token metrics;
- report bootstrap confidence intervals for success differences when sample size permits;
- record all failures, not only successful runs;
- randomize variant execution order to reduce time/provider drift effects.

Do not overclaim statistical significance from small pilot samples.

## 9. Fairness controls

All variants must have equivalent:

- task information;
- tool capabilities;
- access permissions;
- expected output schema;
- state freshness;
- retry budget;
- model/config when using LLMs.

`SJSON` and `AIR` must share the same `StateStore` implementation where possible.

Do not let AIR receive precomputed semantic structure unavailable to comparison variants unless semantic-compilation cost is separately measured and reported.

## 10. Tokenizer experiment

This is a critical falsification experiment.

For each logical coordination action, generate:

1. human-readable NL;
2. normal JSON;
3. compact JSON/SJSON;
4. readable AIR-Text;
5. optional opcode-aliased AIR printer.

Count tokens across multiple model tokenizers if available.

Questions:

- Does shorter character length actually mean fewer tokens?
- Are abbreviations tokenized poorly?
- Is JSON punctuation overhead material?
- Does a readable IR outperform opaque aliases after instruction overhead is included?

Important: include the **instruction/schema explanation cost** needed for a model to understand a custom AIR syntax. Do not benchmark only standalone payload lines if the real system needs a large repeated grammar prompt.

Also run a prefix-cached scenario separately if the provider supports/records cached input.

## 11. Acceptance/falsification criteria

These are project-defined research thresholds, not established scientific constants.

### Custom syntax is not justified if

Relative to SJSON, AIR achieves:

```text
<20% token/coordination reduction
```

and no meaningful improvement in:

- latency;
- LLM calls;
- task success;
- security/reliability;
- auditability.

Then retain typed AST/runtime and use JSON/schema as the model-facing representation.

### Runtime architecture is promising if

Relative to NL in representative scenarios:

- context/coordination volume reduction is substantial (target >=40% pilot threshold);
- task success is non-inferior within pilot uncertainty;
- unauthorized executed effects = 0 in provided adversarial suite;
- stale/out-of-scope writes are detected;
- critical semantic information is preserved;
- operator audit answers are reconstructable from event/provenance state.

These are MVP gates, not publication claims.

## 12. Benchmark output schema

Suggested JSON Lines records:

```json
{
  "run_id": "...",
  "suite": "smoke",
  "scenario": "long_context.medium",
  "variant": "SJSON",
  "config": {"seed": 1},
  "result": {"success": true, "semantic_score": 1.0},
  "usage": {
    "input_tokens": null,
    "output_tokens": null,
    "coordination_bytes": 423,
    "state_materialized_bytes": 812,
    "agent_calls": 1,
    "tool_calls": 0
  },
  "timing": {"wall_latency_ms": 2.8},
  "security": {
    "rejections": 0,
    "unauthorized_effects_executed": 0
  }
}
```

## 13. Smoke suite

Keep a quick suite suitable for every PR:

- relay basic;
- long-context small;
- shared-edit disjoint;
- shared-edit conflict;
- one forbidden write;
- operator audit minimal.

Target runtime: seconds, no network.

## 14. Full suite

Adds:

- scale sweep;
- multi-tool 5/10/30;
- all adversarial mutations;
- repeated seeded runs;
- optional tokenizer/provider-backed measurements.

## 15. Report structure

Generated report should emphasize deltas:

```text
NL -> JSON      structure effect
JSON -> SJSON   shared-state/ref effect
SJSON -> AIR    IR/runtime incremental effect
AIR -> AIR+OPT  optimizer effect
```

Never publish only `NL vs AIR` as the primary result.
