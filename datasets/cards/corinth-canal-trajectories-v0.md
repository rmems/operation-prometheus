# Dataset Card: corinth-canal trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [corinth-canal-v0.jsonl](../jsonl/corinth-canal-v0.jsonl)  
**Machine card:** [corinth-canal-v0.json](corinth-canal-v0.json)  
**Manifest:** [corinth-canal-v0.manifest.json](../manifests/corinth-canal-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/corinth-canal.md](../../docs/source-repos/corinth-canal.md)

## Source repository

- **Repo:** [rmems/corinth-canal](https://github.com/rmems/corinth-canal)
- **Description:** Turning MoE architecture into SNN quantization (SAAQ — Spiking Adaptive Activity Quantization)
- **Language:** Rust (CUDA paths optional)

## Included PRs (12)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#82](https://github.com/rmems/corinth-canal/pull/82) | repair | repair | gpu-compute | 0.86 |
| [#89](https://github.com/rmems/corinth-canal/pull/89) | validation | validation | gpu-compute | 0.92 |
| [#91](https://github.com/rmems/corinth-canal/pull/91) | feature | feature | ml-infra | 0.62 |
| [#94](https://github.com/rmems/corinth-canal/pull/94) | repair | repair | ml-infra | 0.94 |
| [#95](https://github.com/rmems/corinth-canal/pull/95) | feature | feature | ml-infra | 0.58 |
| [#96](https://github.com/rmems/corinth-canal/pull/96) | feature | validation | tools | 0.78 |
| [#125](https://github.com/rmems/corinth-canal/pull/125) | review-to-patch | review-to-patch | ml-infra | 0.90 |
| [#126](https://github.com/rmems/corinth-canal/pull/126) | review-to-patch | review-to-patch | gpu-compute | 0.95 |
| [#127](https://github.com/rmems/corinth-canal/pull/127) | review-to-patch | review-to-patch | tools | 0.90 |
| [#128](https://github.com/rmems/corinth-canal/pull/128) | review-to-patch | review-to-patch | ml-infra | 0.90 |
| [#138](https://github.com/rmems/corinth-canal/pull/138) | repair | repair | gpu-compute | 0.90 |
| [#142](https://github.com/rmems/corinth-canal/pull/142) | review-to-patch | review-to-patch | ml-infra | 0.90 |

## Narrative buckets

1. **Quantization repair** — Q6_K (#82) and IQ3_M/Int4 (#94) dequantization pathways; synthetic-fallback fixes; packed-format size bugs.
2. **CUDA validation discipline** — Tier 0–5 ladder, smoke asserts, Compute Sanitizer, teardown-order fix (#89).
3. **Model onboarding / backends** — Safetensors loading + experiment schema contracts (#91).
4. **SAAQ experiment operations** — adapter configs, multi-model run matrix, cloud lineup (#95).
5. **Config/schema contract tooling** — local dry-run validator and sprint summarizer CLIs (#96).
6. **GH#118 GGUF/Safetensors refactor wave (2026-08-18)** — unify family inference (#125), checkpoint `gguf/` split (#128), config validation helpers (#127), GGUF synapse source selection (#126) and its recovery onto `main` (#138), ROUTING_MODE dense_sim/stub_uniform bugfix (#142).

## Intended training uses

- Local SFT / process-supervision for coding agents working on SAAQ, MoE quant, and CUDA validation.
- Repair trajectories: issue → dequant/fix → tests → merge; plus #138 recovering a squash-merge that never landed.
- Validation trajectories: multi-tier evidence checklists.
- Review-to-patch: GH#118 family PRs and #142, with Gemini/Codex line comments kept after bot filtering.
- Schema v0.1 `training_use` includes `feature`; #91/#95 map to `feature`. #96 remains `validation` via the legacy override.

## Known limitations (v0)

- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- Review noise is high; CodeAnt/Macroscope/Codecov are filtered; engineering review bots (Gemini/Codex) are retained.
- `#138` emits only 2 unique review signals after dedupe; it is in the set as the repair of `#126`, not as a yield leader. `#126` itself is GitHub-merged but its tree never reached `main`.
- Absolute home paths and secret-like tokens are redacted.
- Linked GitHub issues are often thin Linear stubs; PR bodies carry primary issue context.
- Solo-maintainer merges: multi-human review is limited.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py \
  --repo rmems/corinth-canal --pr 82,89,91,94,95,96,125,126,127,128,138,142 \
  --out-dir datasets/raw/corinth-canal \
  --skip-existing

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/corinth-canal \
  --card datasets/cards/corinth-canal-v0.json \
  --out datasets/jsonl/corinth-canal-v0.jsonl \
  --pr 82,89,91,94,95,96,125,126,127,128,138,142

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/corinth-canal-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/corinth-canal-v0.jsonl
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. GH#118 wave added 2026-08-18.
