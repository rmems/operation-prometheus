# Dataset Card: spike-viz trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [spike-viz-v0.jsonl](../jsonl/spike-viz-v0.jsonl)  
**Machine card:** [spike-viz-v0.json](spike-viz-v0.json)  
**Manifest:** [spike-viz-v0.manifest.json](../manifests/spike-viz-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/spike-viz.md](../../docs/source-repos/spike-viz.md)

## Source repository

- **Repo:** [rmems/spike-viz](https://github.com/rmems/spike-viz)
- **Description:** CPU spike visualization (axon-encoder export contract, loaders, raster PNG)
- **Language:** Python

## Included PRs (3)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#24](https://github.com/rmems/spike-viz/pull/24) | feature | feature | visualization | 0.95 |
| [#23](https://github.com/rmems/spike-viz/pull/23) | review-to-patch | review-to-patch | io | 0.95 |
| [#22](https://github.com/rmems/spike-viz/pull/22) | feature | feature | io | 0.90 |

## Narrative buckets

1. **Export + loaders** — package skeleton and fail-loud schema IO (#22).
2. **Review-to-patch** — #23 answers #22's review (meta, geometry, dtypes, license).
3. **Raster renderer** — CPU sparse/dense → PNG (#24).

## Collection pipeline

```bash
export GITHUB_TOKEN="$(gh auth token)"; unset GH_TOKEN
python scripts/collect_pr_records.py \
  --repo rmems/spike-viz --pr 24,23,22 \
  --out-dir datasets/raw/rmems_spike-viz

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_spike-viz \
  --card datasets/cards/spike-viz-v0.json \
  --out datasets/jsonl/spike-viz-v0.jsonl \
  --pr 24,23,22

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/spike-viz-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/spike-viz-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history. Extracted 2026-08-20 for Wave C (issue #29).
