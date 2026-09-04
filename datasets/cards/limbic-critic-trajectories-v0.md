# Dataset Card: limbic-critic trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [limbic-critic-v0.jsonl](../jsonl/limbic-critic-v0.jsonl)  
**Machine card:** [limbic-critic-v0.json](limbic-critic-v0.json)  
**Manifest:** [limbic-critic-v0.manifest.json](../manifests/limbic-critic-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/limbic-critic.md](../../docs/source-repos/limbic-critic.md)

## Source repository

- **Repo:** [rmems/limbic-critic](https://github.com/rmems/limbic-critic)
- **Description:** Neuromodulatory RL critic
- **Language:** Rust

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#30](https://github.com/rmems/limbic-critic/pull/30) | feature | feature | snn | 0.95 |
| [#29](https://github.com/rmems/limbic-critic/pull/29) | repair | repair | api | 0.95 |
| [#2](https://github.com/rmems/limbic-critic/pull/2) | repair | repair | snn | 0.75 |
| [#3](https://github.com/rmems/limbic-critic/pull/3) | repair | repair | api | 0.75 |

## Narrative buckets

1. **Acetylcholine semantics** — drop the 0.5 placeholder (#30).
2. **Crate decoupling** — local ModulatorVector (#29) and modular-crate follow-on (#3).
3. **Rename from spikenaut-reward** (#2).

## Known limitations (v0)

- None of these four PRs carry close-keyword issues.
- #2/#3 quality 0.75 (thin review after bot filter).
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo rmems/limbic-critic --pr 30,29,2,3 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/rmems_limbic-critic --card datasets/cards/limbic-critic-v0.json --out datasets/jsonl/limbic-critic-v0.jsonl --pr 30,29,2,3
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/limbic-critic-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/limbic-critic-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
