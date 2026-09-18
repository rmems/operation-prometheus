# CI contracts

Operation Prometheus splits **fast PR gates** from **release** and **weekly**
jobs. CI exists to enforce corpus correctness; it is not a training product.

## Pull requests (no `HF_TOKEN`)

These jobs run on every PR alongside the existing `lint`, `test`, `validate`,
`status-up-to-date`, and `shared-files-guard` jobs:

- `trajectory-contract` — v0/v1 schemas, fixture round-trips, unique IDs,
  SHA-256 references, license/policy, sourced actors, secrets, private URIs,
  local paths, and nonterminal positives.
- `corpus-integrity` — every JSONL row resolves to the frozen v0.7 inventory,
  every candidate has a reason, inventory/JSONL/manifest hashes match,
  exact/near-duplicate groups are written as JSONL, mutable/open rows cannot
  enter a positive release, silent truncation and checklist-as-CI are rejected.
- `consumer-contract` — sample `messages` and instruction/input/output rows are
  loaded through Agoge Forger's `normalize_row` with provenance sidecars.
  No GPU, no model download, no `HF_TOKEN`.

## Release environment

`hf-release-verify` runs only from `workflow_dispatch`, published GitHub
releases, or version tags, inside the protected `release` environment. It
checks JSONL/Parquet checksums, a resumable upload plan, metadata/configs, a
pinned-revision download when `HF_TOKEN` is present, and refuses to overwrite an
immutable `vMAJOR.MINOR.PATCH` tag.

## Weekly read-only audit

`source-inventory-audit` compares live public GitHub repositories and terminal
PRs to `datasets/inventory/v0.7/`. It uploads a report and does not open source
issues or otherwise mutate source repositories.
