# Dataset Card: corinth-canal trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [corinth-canal-v0.jsonl](../jsonl/corinth-canal-v0.jsonl)  
**Machine card:** [corinth-canal-v0.json](corinth-canal-v0.json)  
**Manifest:** [corinth-canal-v0.manifest.json](../manifests/corinth-canal-v0.manifest.json)  
**Shortlist source:** [docs/source-repos.md](../../docs/source-repos.md)

## Source repository

- **Repo:** [rmems/corinth-canal](https://github.com/rmems/corinth-canal)
- **Description:** Turning MoE architecture into SNN quantization (SAAQ — Spiking Adaptive Activity Quantization)
- **Language:** Rust (CUDA paths optional)

## Included PRs (6)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#82](https://github.com/rmems/corinth-canal/pull/82) | repair | repair | gpu-compute | 0.86 |
| [#89](https://github.com/rmems/corinth-canal/pull/89) | validation | validation | gpu-compute | 0.92 |
| [#91](https://github.com/rmems/corinth-canal/pull/91) | feature | other | ml-infra | 0.62 |
| [#94](https://github.com/rmems/corinth-canal/pull/94) | repair | repair | ml-infra | 0.94 |
| [#95](https://github.com/rmems/corinth-canal/pull/95) | feature | other | ml-infra | 0.58 |
| [#96](https://github.com/rmems/corinth-canal/pull/96) | feature | validation | tools | 0.78 |

## Narrative buckets

1. **Quantization repair** — Q6_K (#82) and IQ3_M/Int4 (#94) dequantization pathways; synthetic-fallback fixes; packed-format size bugs.
2. **CUDA validation discipline** — Tier 0–5 ladder, smoke asserts, Compute Sanitizer, teardown-order fix (#89).
3. **Model onboarding / backends** — Safetensors loading + experiment schema contracts (#91).
4. **SAAQ experiment operations** — adapter configs, multi-model run matrix, cloud lineup (#95).
5. **Config/schema contract tooling** — local dry-run validator and sprint summarizer CLIs (#96).

## Intended training uses

- Local SFT / process-supervision for coding agents working on SAAQ, MoE quant, and CUDA validation.
- Repair trajectories: issue → dequant/fix → tests → merge.
- Validation trajectories: multi-tier evidence checklists.
- Review-to-patch signal is present primarily via Gemini/Codex line comments kept after bot filtering.

## Known limitations (v0)

- Schema `training_use` has no `feature` enum value; feature-bucket PRs map to `other` (task_type remains `feature`).
- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- Review noise is high; CodeAnt/Macroscope/Codecov are filtered; engineering review bots (Gemini/Codex) are retained.
- Absolute home paths and secret-like tokens are redacted.
- Linked GitHub issues are often thin Linear stubs; PR bodies carry primary issue context.
- Solo-maintainer merges: multi-human review is limited.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py \
  --repo rmems/corinth-canal --pr 82,89,91,94,95,96 \
  --out-dir datasets/raw/corinth-canal

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/corinth-canal \
  --card datasets/cards/corinth-canal-v0.json \
  --out datasets/jsonl/corinth-canal-v0.jsonl

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/corinth-canal-v0.jsonl
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental.
