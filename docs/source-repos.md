# Source Repositories and Extraction Shortlists

**Status**: Draft (implements GitHub issue #4)

Operation Prometheus extracts trajectory datasets from public repositories. This document tracks which repos and PRs are targeted for extraction.

## Extraction Format

All trajectories are extracted as JSONL records conforming to [pr_trajectory.schema.json](../schemas/pr_trajectory.schema.json) (schema v0). One record per PR. See [datasets/README.md](../datasets/README.md) for commit rules.

---

## corinth-canal

**Repo**: [rmems/corinth-canal](https://github.com/rmems/corinth-canal)
**Description**: Turning MOE architecture into SNN quantization
**Language**: Rust
**Status**: v0 shortlist (not yet extracted)

### Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#82](https://github.com/rmems/corinth-canal/pull/82) | Q6_K dequantized GPU synapse path for DeepSeek2 | gpu-compute, ml-infra | repair | Complex dequantization with iterative fix/validation loop. 17 commits, 89+ tests. |
| [#89](https://github.com/rmems/corinth-canal/pull/89) | CUDA validation ladder | gpu-compute, testing | validation | Tier 0-5 CUDA validation with Compute Sanitizer. Fixes teardown order. Multi-step validation trajectory. |
| [#91](https://github.com/rmems/corinth-canal/pull/91) | Safetensors backend + experiment schema | ml-infra | feature | 3 issues combined: new backend, schema standardization, config. 35 files changed. |
| [#94](https://github.com/rmems/corinth-canal/pull/94) | IQ3_M and Int4 dequantization pathways | ml-infra | repair | Extends quantization across GGUF and Safetensors. Targeted 6-file change. |
| [#95](https://github.com/rmems/corinth-canal/pull/95) | Model adapter configs + SAAQ run matrix | ml-infra, config | feature | Multi-model run matrix with validation gates. 8 new model families. |
| [#96](https://github.com/rmems/corinth-canal/pull/96) | Local SAAQ validator and sprint summarizer | tools, infra | feature | CLI tooling for dry-run validation and sprint reporting. |

### PR Details

#### PR #82 — Q6_K dequantized GPU synapse path
- **URL**: https://github.com/rmems/corinth-canal/pull/82
- **Merged**: 2026-05-25
- **Commits**: 17
- **Files changed**: 7
- **Why high-signal**: Adds Q6_K (ggml type 14) dequantized GPU synapse loading. Shows a full review→fix→validation trajectory with 89 passing tests. Introduces `dequantize_row_q6_k`, refactors shared `load_dequant_synapse` helper, extracts GGML constants into new module.
- **Dataset bucket**: `repair` — iterative dequantization implementation with validation ladder
- **Closes**: rmems/corinth-canal#39

#### PR #89 — CUDA validation ladder
- **URL**: https://github.com/rmems/corinth-canal/pull/89
- **Merged**: 2026-05-27
- **Commits**: 3
- **Files changed**: 11
- **Why high-signal**: Adds Tier 0-5 CUDA validation documentation and extends `gpu_smoke_test` with configurable tick counts and deterministic state assertions. Fixes CUDA teardown order (device buffers before context). Clean Compute Sanitizer memcheck/synccheck/racecheck pass.
- **Dataset bucket**: `validation` — multi-tier validation trajectory with sanitizer evidence
- **Closes**: rmems/corinth-canal#74

#### PR #91 — Safetensors backend + experiment schema
- **URL**: https://github.com/rmems/corinth-canal/pull/91
- **Merged**: 2026-05-27
- **Commits**: 6
- **Files changed**: 35
- **Why high-signal**: Combines 3 issues (#75, #76, #85) into a cohesive feature: safetensors tensor loading with memory-mapped shard access, `ExperimentBundle` schema for downstream Surrogate_Viz.jl ingestion, config/dotenv standardization. Massive scope with clean validation.
- **Dataset bucket**: `feature` — large multi-issue feature with schema design
- **Closes**: #75, #76, #85

#### PR #94 — IQ3_M and Int4 dequantization pathways
- **URL**: https://github.com/rmems/corinth-canal/pull/94
- **Merged**: 2026-05-27
- **Commits**: 11
- **Files changed**: 6
- **Why high-signal**: Adds IQ3_M (GGUF, 111-byte block layout) and Int4 (Safetensors, nibble unpacking) dequantization. Extends `SynapseSource` enum, fixes `expected_tensor_byte_size` for packed formats. Targeted, surgical change.
- **Dataset bucket**: `repair` — targeted quantization extension with bug fix
- **Closes**: rmems/corinth-canal#92

#### PR #95 — Model adapter configs + SAAQ run matrix
- **URL**: https://github.com/rmems/corinth-canal/pull/95
- **Merged**: 2026-05-28
- **Commits**: 4
- **Files changed**: 15
- **Why high-signal**: Adds 8 new `ModelFamily` variants, `ModelAdapterConfig`/`RunEntry`/`RunMatrix` structs with `validate()`, 20 static adapter entries, multi-model run matrix (21 runs), cloud lineup rewrite. Shows config-driven feature with validation gates.
- **Dataset bucket**: `feature` — config-driven multi-model infrastructure
- **Closes**: #80, #83, #84

#### PR #96 — Local SAAQ validator and sprint summarizer
- **URL**: https://github.com/rmems/corinth-canal/pull/96
- **Merged**: 2026-05-28
- **Commits**: 4
- **Files changed**: 4
- **Why high-signal**: Adds `validate_local_saaq` (dry-run matrix validator with `--check-paths`) and `summarize_local_saaq` (markdown sprint summary from run artifacts). Tools-for-tools trajectory.
- **Dataset bucket**: `feature` — CLI tooling for experiment validation and reporting
- **Closes**: rmems/corinth-canal#90 (partial — Lane A + D)

---

## Adding New Source Repos

To add a new source repository:
1. Add a section above with repo metadata
2. Create a PR shortlist with at least 5 high-signal PRs
3. Assign each PR a dataset bucket (`repair`, `validation`, `feature`, `review-to-patch`, etc.)
4. Create a metadata card in `datasets/cards/`
5. Reference this doc from the card

See [data-policy.md](data-policy.md) for allowed sources and exclusions.
