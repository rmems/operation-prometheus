# Dataset Card: nir-rs trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [nir-rs-v0.jsonl](../jsonl/nir-rs-v0.jsonl)  
**Machine card:** [nir-rs-v0.json](nir-rs-v0.json)  
**Manifest:** [nir-rs-v0.manifest.json](../manifests/nir-rs-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/nir-rs.md](../../docs/source-repos/nir-rs.md)

## Source repository

- **Repo:** [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs)
- **Description:** Rust NIR interchange
- **Language:** Rust

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#20](https://github.com/Limen-Neural/nir-rs/pull/20) | feature | feature | io | 0.90 |
| [#23](https://github.com/Limen-Neural/nir-rs/pull/23) | repair | repair | io | 0.90 |
| [#18](https://github.com/Limen-Neural/nir-rs/pull/18) | feature | feature | io | 0.95 |
| [#24](https://github.com/Limen-Neural/nir-rs/pull/24) | feature | feature | api | 0.95 |

## Narrative buckets

1. **Core IR then HDF5** — in-memory graph (#18) then opt-in `.nir` IO (#20).
2. **Untrusted-read harden** (#23, `task_type` security).
3. **Serde graph** independent of hdf5 (#24).

## Known limitations (v0)

- #20 patch is truncated to ~96 KiB.
- Docker dual-publish #38 excluded by policy.
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo Limen-Neural/nir-rs --pr 20,23,18,24 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/Limen-Neural_nir-rs --card datasets/cards/nir-rs-v0.json --out datasets/jsonl/nir-rs-v0.jsonl --pr 20,23,18,24
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/nir-rs-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/nir-rs-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
