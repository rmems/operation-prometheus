# Dataset Card: xai-dissect trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [xai-dissect-v0.jsonl](../jsonl/xai-dissect-v0.jsonl)  
**Machine card:** [xai-dissect-v0.json](xai-dissect-v0.json)  
**Manifest:** [xai-dissect-v0.manifest.json](../manifests/xai-dissect-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/xai-dissect.md](../../docs/source-repos/xai-dissect.md)

## Source repository

- **Repo:** [rmems/xai-dissect](https://github.com/rmems/xai-dissect)
- **Description:** Grok-1 shard dissection, coverage manifests, grok-ozempic export / quant-plan contract
- **Language:** Rust

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#32](https://github.com/rmems/xai-dissect/pull/32) | feature | feature | export | 0.95 |
| [#34](https://github.com/rmems/xai-dissect/pull/34) | feature | feature | export | 0.90 |
| [#24](https://github.com/rmems/xai-dissect/pull/24) | feature | feature | ml-infra | 0.95 |
| [#36](https://github.com/rmems/xai-dissect/pull/36) | feature | feature | quantization | 0.95 |

## Narrative buckets

1. **Export contract** — grok-ozempic handoff + `quant-plan` (#32); conversion-manifest Markdown (#34).
2. **Coverage validation** — fail-closed 770-tensor inventory (#24).
3. **Planning surfaces** — pilot-plan, route-preservation, GO/NO-GO (#36).

**Not included:** #48 bulk CI (Qodana/Codecov/Sentry).

## Collection pipeline

```bash
export GITHUB_TOKEN="$(gh auth token)"; unset GH_TOKEN
python scripts/collect_pr_records.py \
  --repo rmems/xai-dissect --pr 32,34,24,36 \
  --out-dir datasets/raw/rmems_xai-dissect

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_xai-dissect \
  --card datasets/cards/xai-dissect-v0.json \
  --out datasets/jsonl/xai-dissect-v0.jsonl \
  --pr 32,34,24,36

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/xai-dissect-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/xai-dissect-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history. Extracted 2026-08-20 for Wave C (issue #29).
