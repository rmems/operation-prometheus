# Dataset Card: limen-axon-encoder trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [limen-axon-encoder-v0.jsonl](../jsonl/limen-axon-encoder-v0.jsonl)  
**Machine card:** [limen-axon-encoder-v0.json](limen-axon-encoder-v0.json)  
**Manifest:** [limen-axon-encoder-v0.manifest.json](../manifests/limen-axon-encoder-v0.manifest.json)  
**Shortlist source:** [docs/source-repos.md](../../docs/source-repos.md) (Limen-Neural section)

## Source repository

- **Repo:** [Limen-Neural/axon-encoder](https://github.com/Limen-Neural/axon-encoder)
- **Org:** [Limen-Neural](https://github.com/Limen-Neural) (public SNN stack; owner access available, public history only for this dataset)
- **Language:** Rust

## Included PRs (3)

| PR | Bucket (card) | Schema `training_use` | Domain | Focus |
|----|---------------|----------------------|--------|--------|
| [#37](https://github.com/Limen-Neural/axon-encoder/pull/37) | review-to-patch | review-to-patch | snn / api | Neuromodulator gain curves |
| [#50](https://github.com/Limen-Neural/axon-encoder/pull/50) | repair | repair | security | RNG swap + tests |
| [#41](https://github.com/Limen-Neural/axon-encoder/pull/41) | review-to-patch | review-to-patch | api | Encoder standardization |

## Known limitations (v0)

- Review noise is high (CodeRabbit/Gitar/Devin/etc.); engineering review bots retained after filter.
- Large patches may be truncated (~96 KiB trajectory budget).
- Solo/owner-driven merges: multi-human review may be limited.
- **Not for:** private Limen-Neural history, secrets, model weights, closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py \
  --repo Limen-Neural/axon-encoder --pr 37,50,41 \
  --out-dir datasets/raw/Limen-Neural_axon-encoder

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/Limen-Neural_axon-encoder \
  --card datasets/cards/limen-axon-encoder-v0.json \
  --out datasets/jsonl/limen-axon-encoder-v0.jsonl

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/limen-axon-encoder-v0.jsonl
```
