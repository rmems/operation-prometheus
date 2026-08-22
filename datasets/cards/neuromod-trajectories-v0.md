# Dataset Card: neuromod trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [neuromod-v0.jsonl](../jsonl/neuromod-v0.jsonl)  
**Machine card:** [neuromod-v0.json](neuromod-v0.json)  
**Manifest:** [neuromod-v0.manifest.json](../manifests/neuromod-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/neuromod.md](../../docs/source-repos/neuromod.md)

## Source repository

- **Repo:** [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod)
- **Description:** Core SNN models and neuromodulator API (LIF/HH/FHN/Hebbian, domain-agnostic modulators)
- **Language:** Rust

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#5](https://github.com/Limen-Neural/neuromod/pull/5) | feature | feature | snn | 0.95 |
| [#8](https://github.com/Limen-Neural/neuromod/pull/8) | repair | repair | snn | 0.75 |
| [#9](https://github.com/Limen-Neural/neuromod/pull/9) | bug-prediction | bug-prediction | api | 0.85 |
| [#2](https://github.com/Limen-Neural/neuromod/pull/2) | review-to-patch | review-to-patch | snn | 0.85 |
| [#15](https://github.com/Limen-Neural/neuromod/pull/15) | review-to-patch | review-to-patch | ml-infra | 0.95 |

## Narrative buckets

1. **Foundational neuron models** — Lapicque / HH / FHN / classical Hebbian (#5).
2. **HH + crate standalone** — rewrite rest/reset behavior under a “bench warnings” title (#8).
3. **Neutral API** — dynamic dimensions and trait purge (#9); mining/HFT purge (#2); generic neuromodulator names (#15).

## Intended training uses

- Local SFT for coding agents working on SNN primitives and neuromodulator APIs.
- Feature: adding biophysical neuron modules.
- Review-to-patch: domain-agnostic refactor waves with retained review comments.

## Known limitations (v0)

- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- Review noise is high; Copilot/CodeAnt are filtered; engineering review bots (Gemini/Codex) are retained.
- `#8` and `#9` keep only 2 unique signals after the cap/filter.
- Solo-maintainer merges: multi-human review is limited.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
unset GH_TOKEN
python3 scripts/collect_pr_records.py \
  --repo Limen-Neural/neuromod --pr 5,8,9,2,15

python3 scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/Limen-Neural_neuromod \
  --card datasets/cards/neuromod-v0.json \
  --out datasets/jsonl/neuromod-v0.jsonl \
  --pr 5,8,9,2,15 --strict

python3 scripts/validate_jsonl.py --strict-policy datasets/jsonl/neuromod-v0.jsonl

python3 scripts/build_manifest.py --jsonl datasets/jsonl/neuromod-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-20 for Limen Wave B+ (operation-prometheus #28).
