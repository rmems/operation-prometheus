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

## Data extracts stay in their own lane

Extract PRs run in parallel, so an extract must touch **only its own files**. The
`shared-files-guard` CI job enforces the shared-file part of that rule: a
data-labeled PR that edits any file on its denylist is rejected.

| Instead of editing… | Do this |
|---------------------|---------|
| `STATUS.md` | Nothing — generated from `datasets/manifests/`. Do not commit it (the guard rejects that). |
| `scripts/lib/normalize.py` override dicts | Put `domain_by_pr` / `task_type_by_pr` / `linked_issues_by_pr` on your dataset card. |
| `scripts/lib/bots.py` / `scripts/lib/quality.py` | Nothing — bot stripping and quality scoring are pipeline code. Label the PR `pipeline` if they genuinely need to change. |
| `tests/test_collect_and_normalize.py` | Add `tests/test_overrides_<repo>.py`. |
| `docs/source-repos.md` (stub) | Add `docs/source-repos/<repo>.md` with an `<!-- index: … -->` line near the top. |
| `docs/source-repos/_index.md` | Nothing — its Index table is generated from the per-repo docs' index lines. |
| `README.md` shortlist bullets | Nothing — link from your `docs/source-repos/<repo>.md`. |

So a new extract adds: a card, a JSONL, a manifest, `docs/source-repos/<repo>.md`
(carrying its own index line), and optionally `tests/test_overrides_<repo>.py`.
Nothing shared at all.

Pipeline or schema work legitimately edits the shared files — label those PRs
`pipeline` or `schema` and the guard stands down.

## Validation

Before committing, run:

```bash
ruff check scripts/
pytest -q
if ls datasets/jsonl/*.jsonl 1>/dev/null 2>&1; then
  python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
else
  echo "No JSONL files found; skipping schema validation."
fi
```
