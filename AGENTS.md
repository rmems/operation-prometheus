# Operation Prometheus Agent Guide

Operation Prometheus converts public GitHub engineering history into structured JSON/JSONL trajectory datasets for local coding, research, and agentic models.

## Prime Directive

Preserve the engineering trajectory:

issue/review signal → code state → patch/fix → validation → outcome

## Current Priorities

1. Keep the repo small and inspectable.
2. Build schemas before large extractors.
3. Use JSON/JSONL as the first dataset format.
4. Start with high-signal `corinth-canal` PRs.
5. Prefer read-only GitHub collection scripts before any write automation.

## Do Not

- Do not commit secrets, credentials, local config, or private files.
- Do not commit large raw datasets blindly.
- Do not commit model weights directly to this repo.
- Do not use raw closed-model chat logs as the primary training corpus.
- Do not overwrite existing project structure unless explicitly asked.

## Validation

Before committing, run:

```bash
ruff check scripts || true
pytest -q || true
python scripts/validate_jsonl.py datasets/jsonl/*.jsonl || true
