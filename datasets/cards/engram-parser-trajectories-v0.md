# Dataset Card: engram-parser trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [engram-parser-v0.jsonl](../jsonl/engram-parser-v0.jsonl)  
**Machine card:** [engram-parser-v0.json](engram-parser-v0.json)  
**Manifest:** [engram-parser-v0.manifest.json](../manifests/engram-parser-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/engram-parser.md](../../docs/source-repos/engram-parser.md)

## Source repository

- **Repo:** [rmems/engram-parser](https://github.com/rmems/engram-parser)
- **Description:** Zero-dep GGUF parser and per-expert MoE weight extractor (wire layouts, not dequant)
- **Language:** Rust

## Included PRs (1)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#44](https://github.com/rmems/engram-parser/pull/44) | feature | feature | ml-infra | 0.90 |

## Narrative buckets

1. **GGUF v3 + IQ wire layouts** — layout parse, packed `byte_len`, T1 large MoE pilots (#44). Dependabot-heavy history meant no second real-code PR survived yield/noise filters.

## Collection pipeline

```bash
export GITHUB_TOKEN="$(gh auth token)"; unset GH_TOKEN
python scripts/collect_pr_records.py \
  --repo rmems/engram-parser --pr 44 \
  --out-dir datasets/raw/rmems_engram-parser

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_engram-parser \
  --card datasets/cards/engram-parser-v0.json \
  --out datasets/jsonl/engram-parser-v0.jsonl \
  --pr 44

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/engram-parser-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/engram-parser-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history. Extracted 2026-08-20 for Wave C (issue #29).
