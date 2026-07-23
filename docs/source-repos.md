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
**Status**: v0 **extracted** (2026-07-21) — see [datasets/jsonl/corinth-canal-v0.jsonl](../datasets/jsonl/corinth-canal-v0.jsonl)

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
- **Why high-signal**: Combines 3 issues (rmems/corinth-canal#75, rmems/corinth-canal#76, rmems/corinth-canal#85) into a cohesive feature: safetensors tensor loading with memory-mapped shard access, `ExperimentBundle` schema for downstream Surrogate_Viz.jl ingestion, config/dotenv standardization. Massive scope with clean validation.
- **Dataset bucket**: `feature` — large multi-issue feature with schema design
- **Closes**: rmems/corinth-canal#75, rmems/corinth-canal#76, rmems/corinth-canal#85

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
- **Closes**: rmems/corinth-canal#80, rmems/corinth-canal#83, rmems/corinth-canal#84

#### PR #96 — Local SAAQ validator and sprint summarizer
- **URL**: https://github.com/rmems/corinth-canal/pull/96
- **Merged**: 2026-05-28
- **Commits**: 4
- **Files changed**: 4
- **Why high-signal**: Adds `validate_local_saaq` (dry-run matrix validator with `--check-paths`) and `summarize_local_saaq` (markdown sprint summary from run artifacts). Tools-for-tools trajectory.
- **Dataset bucket**: `feature` — CLI tooling for experiment validation and reporting
- **Closes**: rmems/corinth-canal#90 (partial — Lane A + D)

---

## grok-ozempic

**Repo**: [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic)  
**Description**: SNN-logic ternary quantization for Grok-1 MoE (xai-dissect manifests, GOZ1 packs, SAAQ artifact validation)  
**Language**: Rust  
**Status**: v0 shortlist (not yet extracted)  
**Metadata card**: [datasets/cards/grok-ozempic-v0.json](../datasets/cards/grok-ozempic-v0.json)

### Shortlisted PRs (grok-ozempic)

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#29](https://github.com/rmems/grok-ozempic/pull/29) | Full test coverage, alignment verification, Docker CI | validation, CI | validation | BackendKernel becomes fallible; Local/Myelin parity tests; dry-run alignment guards; Docker + cargo audit. Closes #16, #22, #27. |
| [#26](https://github.com/rmems/grok-ozempic/pull/26) | Align with xai-dissect inventory | validation | validation | 770-tensor inventory + structural manifest; replaces heuristic dry-run counts. Closes #22. |
| [#24](https://github.com/rmems/grok-ozempic/pull/24) | SAAQ artifact validation flow | validation | validation | Multi-step convert/validate ladder with path/symlink hardening. Closes #13–#15, #17–#19. |
| [#25](https://github.com/rmems/grok-ozempic/pull/25) | myelin-accelerator as CUDA backend | ml-infra | feature | CUDA ownership boundary via BackendKernel + DryRunPlanner. Closes #21. |
| [#11](https://github.com/rmems/grok-ozempic/pull/11) | xai-dissect compatible artifact generation | ml-infra | feature | Artifact IR, detector/validator, CLI generate/validate. Closes #10. |
| [#8](https://github.com/rmems/grok-ozempic/pull/8) | Wire xai-dissect manifest into quantization pipeline | ml-infra | feature | Real pipeline consumption + parity/divergence tests. Advances #6. |

### Why these (and not others)

- Prefer issue-linked validation ladders and contract-hardening over pure docs (`#12`, `#23`) or early scaffold (`#1`, `#2`).
- `#33` is review-noise heavy (test dedupe after #29); optional secondary only.
- Large diffs (#26, #11, #24) will need hunk truncation at extract time.

### Candidate next: myelin-accelerator

[rmems/myelin-accelerator](https://github.com/rmems/myelin-accelerator) is thinner (8 merged PRs) but high CUDA/SNN fit. Prefer after grok-ozempic extraction:

| PR | Notes |
|----|-------|
| [#18](https://github.com/rmems/myelin-accelerator/pull/18) | Bitpacking + GPU CI + 62 tests + benches (best overall) |
| [#2](https://github.com/rmems/myelin-accelerator/pull/2) | Kernel routing/SAT reduce (filter `target/` noise) |
| [#6](https://github.com/rmems/myelin-accelerator/pull/6) / [#7](https://github.com/rmems/myelin-accelerator/pull/7) | Feature-gated CUDA + review→patch hardening chain |
| [#4](https://github.com/rmems/myelin-accelerator/pull/4) | SAT cust launchers |
| watch [#22](https://github.com/rmems/myelin-accelerator/pull/22) | Open CUDA quality gate when merged |

---

## Adding New Source Repos

To add a new source repository:
1. Add a section above with repo metadata
2. Create a PR shortlist with at least 5 high-signal PRs
3. Assign each PR a dataset bucket (`repair`, `validation`, `feature`, `review-to-patch`, etc.)
4. Create a metadata card in `datasets/cards/`
5. Reference this doc from the card

See [data-policy.md](data-policy.md) for allowed sources and exclusions.

**Schema note:** card buckets may say `feature`, but schema v0 `training_use` has no `feature` value — normalizer maps `feature` → `other` and keeps `task_type: feature`.
