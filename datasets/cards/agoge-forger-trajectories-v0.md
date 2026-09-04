# Dataset Card: agoge-forger trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [agoge-forger-v0.jsonl](../jsonl/agoge-forger-v0.jsonl)  
**Machine card:** [agoge-forger-v0.json](agoge-forger-v0.json)  
**Manifest:** [agoge-forger-v0.manifest.json](../manifests/agoge-forger-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/agoge-forger.md](../../docs/source-repos/agoge-forger.md)

## Source repository

- **Repo:** [rmems/agoge-forger](https://github.com/rmems/agoge-forger)
- **Description:** Local fine-tuning forge (QLoRA/LoRA, JSONL contracts, adapter merge)
- **Language:** Python

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#120](https://github.com/rmems/agoge-forger/pull/120) | feature | feature | ml-infra | 0.90 |
| [#67](https://github.com/rmems/agoge-forger/pull/67) | repair | repair | training | 0.95 |
| [#85](https://github.com/rmems/agoge-forger/pull/85) | repair | repair | ml-infra | 0.85 |
| [#86](https://github.com/rmems/agoge-forger/pull/86) | repair | repair | training | 0.90 |

## Narrative buckets

1. **Frozen eval contracts** — hardened split/eval tree plus Qlty Bandit gate (#120).
2. **TRL 1.x trainer** — SFTTrainer → SFTConfig so train-qlora constructs on the locked stack (#67).
3. **Dataset + export repair** — strict JSONL message content (#85) and Transformers 5 merge save (#86).

## Known limitations (v0)

- #120 patch is truncated to ~96 KiB.
- #86 emits only 2 unique review signals; kept as the merge-export repair pair with #85.
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo rmems/agoge-forger --pr 120,67,85,86 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/rmems_agoge-forger --card datasets/cards/agoge-forger-v0.json --out datasets/jsonl/agoge-forger-v0.jsonl --pr 120,67,85,86
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/agoge-forger-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/agoge-forger-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
