# Dataset Card: SpikeStream.jl trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [spikestream-jl-v0.jsonl](../jsonl/spikestream-jl-v0.jsonl)  
**Machine card:** [spikestream-jl-v0.json](spikestream-jl-v0.json)  
**Manifest:** [spikestream-jl-v0.manifest.json](../manifests/spikestream-jl-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/spikestream-jl.md](../../docs/source-repos/spikestream-jl.md)

## Source repository

- **Repo:** [rmems/SpikeStream.jl](https://github.com/rmems/SpikeStream.jl)
- **Description:** Julia spike-stream feature extraction package (counts, ISI, bursts) at the kinetic-signals boundary
- **Language:** Julia

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#7](https://github.com/rmems/SpikeStream.jl/pull/7) | feature | feature | snn | 0.95 |
| [#25](https://github.com/rmems/SpikeStream.jl/pull/25) | validation | validation | snn | 0.90 |
| [#22](https://github.com/rmems/SpikeStream.jl/pull/22) | repair | repair | api | 0.85 |
| [#21](https://github.com/rmems/SpikeStream.jl/pull/21) | validation | validation | tools | 0.95 |

## Narrative buckets

1. **Package identity** — re-scope around spike-stream feature extraction (#7).
2. **Boundary with kinetic-signals** — frozen fixtures (#25) and delete Hurst/Hawkes/GBM proxies (#22).
3. **Streaming benches** — BenchmarkTools harness (#21).

## Intended training uses

- Feature: Julia spike-feature APIs.
- Validation: golden fixtures and benches.
- Repair: API amputation at a language-package boundary.

## Known limitations (v0)

- Four-PR Wave B+ pilot (not the “at least five” default; SpikeStream has 11 merged PRs and the remainder is CI/docs/license).
- `#18`/`#20` have higher raw review counts but are CI/docs-only — not in this JSONL.
- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
unset GH_TOKEN
python3 scripts/collect_pr_records.py \
  --repo rmems/SpikeStream.jl --pr 7,25,22,21

python3 scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_SpikeStream.jl \
  --card datasets/cards/spikestream-jl-v0.json \
  --out datasets/jsonl/spikestream-jl-v0.jsonl \
  --pr 7,25,22,21 --strict

python3 scripts/validate_jsonl.py --strict-policy datasets/jsonl/spikestream-jl-v0.jsonl

python3 scripts/build_manifest.py --jsonl datasets/jsonl/spikestream-jl-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-20 for Limen Wave B+ (operation-prometheus #28).
