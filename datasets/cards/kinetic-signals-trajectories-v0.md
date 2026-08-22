# Dataset Card: kinetic-signals trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [kinetic-signals-v0.jsonl](../jsonl/kinetic-signals-v0.jsonl)  
**Machine card:** [kinetic-signals-v0.json](kinetic-signals-v0.json)  
**Manifest:** [kinetic-signals-v0.manifest.json](../manifests/kinetic-signals-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/kinetic-signals.md](../../docs/source-repos/kinetic-signals.md)

## Source repository

- **Repo:** [rmems/kinetic-signals](https://github.com/rmems/kinetic-signals)
- **Description:** Streaming signal-processing crate (Hawkes/surprise/stats) at the SpikeStream.jl language boundary
- **Language:** Rust

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#39](https://github.com/rmems/kinetic-signals/pull/39) | validation | validation | telemetry | 0.95 |
| [#35](https://github.com/rmems/kinetic-signals/pull/35) | validation | validation | telemetry | 0.95 |
| [#17](https://github.com/rmems/kinetic-signals/pull/17) | repair | repair | snn | 0.95 |
| [#6](https://github.com/rmems/kinetic-signals/pull/6) | feature | feature | infra | 0.95 |
| [#1](https://github.com/rmems/kinetic-signals/pull/1) | bug-prediction | bug-prediction | ml-infra | 0.75 |

## Narrative buckets

1. **Streaming goldens** — shared_vectors for Hawkes/surprise/stats (#39) and demo coverage (#35).
2. **API amputation** — delete deprecated GBM aliases (#17).
3. **Crate independence** — domain rename + CI (#6); drop third-party crates (#1).

## Intended training uses

- Validation trajectories for cross-language fixture ranges.
- Repair: breaking removal of deprecated aliases.
- Feature: generalize the crate off workspace/third-party deps.

## Known limitations (v0)

- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- `#39` review volume is bot-heavy; 8 unique bodies survive the cap.
- `#1` keeps a single unique review signal.
- Transfer from Limen-Neural → rmems: issue URLs in titles may still say Limen-Neural; card `linked_issues_by_pr` uses the current repo.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
unset GH_TOKEN
python3 scripts/collect_pr_records.py \
  --repo rmems/kinetic-signals --pr 39,35,17,6,1

python3 scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_kinetic-signals \
  --card datasets/cards/kinetic-signals-v0.json \
  --out datasets/jsonl/kinetic-signals-v0.jsonl \
  --pr 39,35,17,6,1 --strict

python3 scripts/validate_jsonl.py --strict-policy datasets/jsonl/kinetic-signals-v0.jsonl

python3 scripts/build_manifest.py --jsonl datasets/jsonl/kinetic-signals-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-20 for Limen Wave B+ (operation-prometheus #28).
