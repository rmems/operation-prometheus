# Dataset Card: LiquidCortex.jl trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [liquidcortex-jl-v0.jsonl](../jsonl/liquidcortex-jl-v0.jsonl)  
**Machine card:** [liquidcortex-jl-v0.json](liquidcortex-jl-v0.json)  
**Manifest:** [liquidcortex-jl-v0.manifest.json](../manifests/liquidcortex-jl-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/liquidcortex-jl.md](../../docs/source-repos/liquidcortex-jl.md)

## Source repository

- **Repo:** [rmems/LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl)
- **Description:** Julia liquid-state machine
- **Language:** Julia

## Included PRs (3)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#45](https://github.com/rmems/LiquidCortex.jl/pull/45) | feature | feature | gpu-compute | 0.95 |
| [#12](https://github.com/rmems/LiquidCortex.jl/pull/12) | repair | repair | snn | 0.95 |
| [#33](https://github.com/rmems/LiquidCortex.jl/pull/33) | validation | validation | snn | 0.90 |

## Narrative buckets

1. **GPU / plasticity step** — experimental `step!` kwargs (#45).
2. **Domain purge** — drop market telemetry, generic LSM dims (#12).
3. **Reference LSM tests** (#33).

## Known limitations (v0)

- Only three domain PRs survived the skip list (action bumps / ImgBot / docs / CI rename #4).
- #33 `Closes #22` restored via `linked_issues_by_pr`.
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo rmems/LiquidCortex.jl --pr 45,12,33 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/rmems_LiquidCortex.jl --card datasets/cards/liquidcortex-jl-v0.json --out datasets/jsonl/liquidcortex-jl-v0.jsonl --pr 45,12,33
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/liquidcortex-jl-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/liquidcortex-jl-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
