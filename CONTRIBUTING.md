# Contributing to AIR

AIR is an experimental research runtime. Changes should preserve reproducibility and the security invariants in [`AGENTS.md`](AGENTS.md).

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Before opening a change

Run the complete local foundation check:

```bash
python -m pytest -q
ruff check .
ruff format --check .
python -m mypy src
```

Use the task queue in [`docs/CODEX_TASKS.md`](docs/CODEX_TASKS.md). Stop at milestone boundaries and keep each change focused.

## Design rules

- Keep the canonical typed model independent from AIR-Text.
- Do not bypass verifier or `StateStore` APIs in later milestones.
- Keep semantic objects immutable.
- Unknown operations/effects must fail closed.
- Preserve provenance and trust labels.
- Prefer deterministic mock agents/tools before provider integrations.
- Add positive, rejection and boundary tests for verifier rules.
- Do not add real irreversible effects to the MVP.

When implementation reveals a genuine specification ambiguity, record the smallest compatible decision in [`docs/DECISIONS.md`](docs/DECISIONS.md) and add a regression test.
