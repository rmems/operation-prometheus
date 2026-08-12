# Datasets

This directory contains generated artifacts for Operation Prometheus trajectory datasets.

**Critical rules (see also root `.gitignore` and [AGENTS.md](../AGENTS.md)):**

- **Do not commit large raw datasets** or full GitHub issue/PR exports here.
- **Do not commit model weights** or other large binary artifacts.
- `datasets/raw/` is intended for local, temporary raw collection output from GitHub (gitignored).
- `datasets/jsonl/` is for cleaned, linked JSONL trajectory records — only commit small example files, schema samples, or cards.
- `datasets/cards/` holds lightweight metadata cards describing datasets (these are safe to commit).

Large data should live outside the repo (e.g. on object storage, Dolt, or a separate private datasets repo) and be referenced via manifests or cards.

## Sibling data root (`PROMETHEUS_DATA_ROOT`)

For scale collects, set a sibling directory so raw dumps never bloat the git tree:

```bash
export PROMETHEUS_DATA_ROOT=~/rmems/prometheus-data   # or /tmp/prometheus-data
# Layout:
#   $PROMETHEUS_DATA_ROOT/raw/<owner_repo>/pr-N.json
```

When `PROMETHEUS_DATA_ROOT` is set and `--out-dir` is omitted, `collect_pr_records.py` writes under that root. Resume multi-hour batches with `--skip-existing`. Discover candidates with `scripts/list_merged_prs.py` (still shortlist before training).

| Commit | Do not commit |
|--------|----------------|
| cards, manifests, small curated JSONL, examples | `$PROMETHEUS_DATA_ROOT/**`, full multi-MB JSONL regenerates |

This keeps the repository small, inspectable, and compliant with the project's prime directive and "Do Not" guidelines.

See:
- [AGENTS.md](../AGENTS.md) for overall rules
- [schemas/pr_trajectory.schema.json](../schemas/pr_trajectory.schema.json) for the canonical trajectory data shape (schema v0)
- [docs/source-repos.md](../docs/source-repos.md) for extraction shortlists and source repo tracking
- [cards/corinth-canal-trajectories-v0.md](cards/corinth-canal-trajectories-v0.md) for the first extracted dataset card
- [../STATUS.md](../STATUS.md) for current extraction status

## Layout notes

- `jsonl/` — curated, schema-valid trajectories (small; commit OK)
- `cards/` — lightweight metadata + human dataset cards
- `manifests/` — per-dataset hashes and per-record quality summary
- `raw/` — local collector output only (gitignored)
- `examples/` — tiny synthetic samples for schema demos
