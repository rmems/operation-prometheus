# corinth-canal

<!-- index: [rmems/corinth-canal](https://github.com/rmems/corinth-canal) | v0 extracted -->

**Repo**: [rmems/corinth-canal](https://github.com/rmems/corinth-canal)
**Description**: Turning MOE architecture into SNN quantization
**Language**: Rust
**Status**: v0 **extracted** (2026-07-21) and **extended** 2026-08-18 with the GH#118 GGUF/Safetensors wave (issue [#24](https://github.com/rmems/operation-prometheus/issues/24) / epic [#32](https://github.com/rmems/operation-prometheus/issues/32)) — see [datasets/jsonl/corinth-canal-v0.jsonl](../../datasets/jsonl/corinth-canal-v0.jsonl)

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#82](https://github.com/rmems/corinth-canal/pull/82) | Q6_K dequantized GPU synapse path for DeepSeek2 | gpu-compute, ml-infra | repair | Complex dequantization with iterative fix/validation loop. 17 commits, 89+ tests. |
| [#89](https://github.com/rmems/corinth-canal/pull/89) | CUDA validation ladder | gpu-compute, testing | validation | Tier 0-5 CUDA validation with Compute Sanitizer. Fixes teardown order. Multi-step validation trajectory. |
| [#91](https://github.com/rmems/corinth-canal/pull/91) | Safetensors backend + experiment schema | ml-infra | feature | 3 issues combined: new backend, schema standardization, config. 35 files changed. |
| [#94](https://github.com/rmems/corinth-canal/pull/94) | IQ3_M and Int4 dequantization pathways | ml-infra | repair | Extends quantization across GGUF and Safetensors. Targeted 6-file change. |
| [#95](https://github.com/rmems/corinth-canal/pull/95) | Model adapter configs + SAAQ run matrix | ml-infra, config | feature | Multi-model run matrix with validation gates. 8 new model families. |
| [#96](https://github.com/rmems/corinth-canal/pull/96) | Local SAAQ validator and sprint summarizer | tools, infra | feature | CLI tooling for dry-run validation and sprint reporting. |
| [#125](https://github.com/rmems/corinth-canal/pull/125) | Unify GGUF/Safetensors family inference (GH#118 PR-1) | ml-infra | review-to-patch | Shared `infer_family_for_format`. 179 kept / 8 emitted / 96 unique. Closes #133. |
| [#126](https://github.com/rmems/corinth-canal/pull/126) | Priority-ordered GGUF synapse source selection (GH#118 PR-2) | gpu-compute | review-to-patch | `select_gguf_synapse` candidate order. 10 kept / 7 unique. GitHub-merged; content missed `main` (see #138). Closes #134. |
| [#127](https://github.com/rmems/corinth-canal/pull/127) | Extract config validation helpers (GH#118 PR-3) | tools | review-to-patch | `validate_initial_config` / `finalize_experts_from_router`. 13 kept / 8 emitted / 10 unique. Closes #135. |
| [#128](https://github.com/rmems/corinth-canal/pull/128) | Split checkpoint.rs into private gguf/ modules (GH#118 PR-4) | ml-infra | review-to-patch | Module split, public API unchanged. 15 kept / 6 unique. |
| [#138](https://github.com/rmems/corinth-canal/pull/138) | Recover priority-ordered GGUF synapse source selection | gpu-compute | repair | Restores #126 onto `main` after squash-merge drop. 5 kept / 2 unique; kept as the repair half of the #126/#138 pair. Closes #134. |
| [#142](https://github.com/rmems/corinth-canal/pull/142) | Accept dense_sim/stub_uniform in ROUTING_MODE | ml-infra | review-to-patch | Env vs lineup routing-mode tables had drifted. 50 kept / 8 emitted / 11 unique. Closes #140. |

## PR Details

### PR #82 — Q6_K dequantized GPU synapse path

- **URL**: https://github.com/rmems/corinth-canal/pull/82
- **Merged**: 2026-05-25
- **Commits**: 17
- **Files changed**: 7
- **Why high-signal**: Adds Q6_K (ggml type 14) dequantized GPU synapse loading. Shows a full review→fix→validation trajectory with 89 passing tests. Introduces `dequantize_row_q6_k`, refactors shared `load_dequant_synapse` helper, extracts GGML constants into new module.
- **Dataset bucket**: `repair` — iterative dequantization implementation with validation ladder
- **Closes**: rmems/corinth-canal#39

### PR #89 — CUDA validation ladder

- **URL**: https://github.com/rmems/corinth-canal/pull/89
- **Merged**: 2026-05-27
- **Commits**: 3
- **Files changed**: 11
- **Why high-signal**: Adds Tier 0-5 CUDA validation documentation and extends `gpu_smoke_test` with configurable tick counts and deterministic state assertions. Fixes CUDA teardown order (device buffers before context). Clean Compute Sanitizer memcheck/synccheck/racecheck pass.
- **Dataset bucket**: `validation` — multi-tier validation trajectory with sanitizer evidence
- **Closes**: rmems/corinth-canal#74

### PR #91 — Safetensors backend + experiment schema

- **URL**: https://github.com/rmems/corinth-canal/pull/91
- **Merged**: 2026-05-27
- **Commits**: 6
- **Files changed**: 35
- **Why high-signal**: Combines 3 issues (rmems/corinth-canal#75, rmems/corinth-canal#76, rmems/corinth-canal#85) into a cohesive feature: safetensors tensor loading with memory-mapped shard access, `ExperimentBundle` schema for downstream Surrogate_Viz.jl ingestion, config/dotenv standardization. Massive scope with clean validation.
- **Dataset bucket**: `feature` — large multi-issue feature with schema design
- **Closes**: rmems/corinth-canal#75, rmems/corinth-canal#76, rmems/corinth-canal#85

### PR #94 — IQ3_M and Int4 dequantization pathways

- **URL**: https://github.com/rmems/corinth-canal/pull/94
- **Merged**: 2026-05-27
- **Commits**: 11
- **Files changed**: 6
- **Why high-signal**: Adds IQ3_M (GGUF, 111-byte block layout) and Int4 (Safetensors, nibble unpacking) dequantization. Extends `SynapseSource` enum, fixes `expected_tensor_byte_size` for packed formats. Targeted, surgical change.
- **Dataset bucket**: `repair` — targeted quantization extension with bug fix
- **Closes**: rmems/corinth-canal#92

### PR #95 — Model adapter configs + SAAQ run matrix

- **URL**: https://github.com/rmems/corinth-canal/pull/95
- **Merged**: 2026-05-28
- **Commits**: 4
- **Files changed**: 15
- **Why high-signal**: Adds 8 new `ModelFamily` variants, `ModelAdapterConfig`/`RunEntry`/`RunMatrix` structs with `validate()`, 20 static adapter entries, multi-model run matrix (21 runs), cloud lineup rewrite. Shows config-driven feature with validation gates.
- **Dataset bucket**: `feature` — config-driven multi-model infrastructure
- **Closes**: rmems/corinth-canal#80, rmems/corinth-canal#83, rmems/corinth-canal#84

### PR #96 — Local SAAQ validator and sprint summarizer

- **URL**: https://github.com/rmems/corinth-canal/pull/96
- **Merged**: 2026-05-28
- **Commits**: 4
- **Files changed**: 4
- **Why high-signal**: Adds `validate_local_saaq` (dry-run matrix validator with `--check-paths`) and `summarize_local_saaq` (markdown sprint summary from run artifacts). Tools-for-tools trajectory.
- **Dataset bucket**: `feature` — CLI tooling for experiment validation and reporting
- **Closes**: rmems/corinth-canal#90 (partial — Lane A + D)

### PR #125 — Unify GGUF/Safetensors family inference (GH#118 PR-1)

- **URL**: https://github.com/rmems/corinth-canal/pull/125
- **Merged**: 2026-07-23
- **Commits**: 16
- **Files changed**: 11
- **Why high-signal**: Collapses duplicated GGUF / Safetensors family-inference post-processing into `infer_family_for_format` while keeping format-specific architecture tables. Highest measured pipeline yield in this wave (179 kept after bot filter, 96 unique bodies, emit cap 8). Maintainer + Codex/Gemini review→patch loop across 16 commits.
- **Dataset bucket**: `review-to-patch` — dense engineering review on a model-loading refactor
- **Closes**: rmems/corinth-canal#133

### PR #126 — Priority-ordered GGUF synapse source selection (GH#118 PR-2)

- **URL**: https://github.com/rmems/corinth-canal/pull/126
- **Merged**: 2026-07-22
- **Commits**: 5
- **Files changed**: 3
- **Why high-signal**: Introduces private `SynapseSelection` / `select_gguf_synapse` with Real→Q8_0→Q5_K→Q6_K→IQ3_M→RoutingF32→SyntheticFallback order. Extracted together with #138: GitHub marked this PR merged off the #125 squash branch, but the code never reached `main`.
- **Dataset bucket**: `review-to-patch` — 10 kept / 7 unique after bot filter and dedupe
- **Closes**: rmems/corinth-canal#134

### PR #127 — Extract config validation helpers (GH#118 PR-3)

- **URL**: https://github.com/rmems/corinth-canal/pull/127
- **Merged**: 2026-07-22
- **Commits**: 3
- **Files changed**: 1
- **Why high-signal**: Pulls `validate_initial_config` and `finalize_experts_from_router` out of `Model::new_with_projector_neurons` with no public API change. Compact, test-preserving refactor with 10 unique review bodies.
- **Dataset bucket**: `review-to-patch` — config-helper extract with retained Gemini/Codex + maintainer signals
- **Closes**: rmems/corinth-canal#135

### PR #128 — Split checkpoint.rs into private gguf/ modules (GH#118 PR-4)

- **URL**: https://github.com/rmems/corinth-canal/pull/128
- **Merged**: 2026-07-21
- **Commits**: 5
- **Files changed**: 11
- **Why high-signal**: Splits the monolithic GGUF checkpoint parser into `src/moe/gguf/{metadata,map,dequant,cuda_register}` behind a compatibility façade. Large surgical refactor (+1329/−1207) without a crate extract.
- **Dataset bucket**: `review-to-patch` — 15 kept / 6 unique
- **Closes**: — (no linked issue; related to #118)

### PR #138 — Recover priority-ordered GGUF synapse source selection

- **URL**: https://github.com/rmems/corinth-canal/pull/138
- **Merged**: 2026-08-08
- **Commits**: 7
- **Files changed**: 6
- **Why high-signal**: Documents and repairs the silent #126 miss: rebase onto `main` after #125 squash + #128 `gguf/` split. Unique-body count is low (2) after the bot filter; kept anyway as the repair half of the #126/#138 pair, not as a yield leader.
- **Dataset bucket**: `repair` — recover dropped GGUF synapse selection onto current `main`
- **Closes**: rmems/corinth-canal#134

### PR #142 — Accept dense_sim/stub_uniform in ROUTING_MODE

- **URL**: https://github.com/rmems/corinth-canal/pull/142
- **Merged**: 2026-08-11
- **Commits**: 3
- **Files changed**: 3
- **Why high-signal**: Two hand-rolled routing-mode spelling tables had drifted, so `ROUTING_MODE=dense_sim` was ignored and runs stayed in `SpikingSim`. Codex + maintainer review on a three-file bugfix; 50 kept / 11 unique.
- **Dataset bucket**: `review-to-patch` — bugfix with a review→patch loop
- **Closes**: rmems/corinth-canal#140

## Measured review-signal yield (2026-08-18)

Counted by replaying each PR's `reviews`, `review_comments`, and `issue_comments` through
[`is_bot_user`](../../scripts/lib/bots.py) and
[`extract_review_signals`](../../scripts/lib/normalize.py) / `_select_deduped_signals`
(hard cap `max_items=8`). Pipeline modules were not edited. Unique bodies are
`extract_review_signals(..., max_items=10000)`.

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #125 | 179 | 8 | 96 | **added** (review-to-patch) |
| #142 | 50 | 8 | 11 | **added** (review-to-patch) |
| #127 | 13 | 8 | 10 | **added** (review-to-patch) |
| #128 | 15 | 6 | 6 | **added** (review-to-patch) |
| #126 | 10 | 7 | 7 | **added** (pair with #138) |
| #138 | 5 | 2 | 2 | **added** (repair; yield below the usual drop line, kept as #126 recovery) |

## Candidate next wave (2026-08-16 scan; extracted 2026-08-18)

The v0 shortlist above predates the GH#118 GGUF/Safetensors refactor wave. Live
merged candidates, with **raw** GitHub API counts (`reviews` / review threads /
issue comments — *pre* bot-filter; pipeline yield is measured at extraction time):

| PR | Title | Reviews | Threads | Comments | Size | Merged | Closes |
|----|-------|---------|---------|----------|------|--------|--------|
| [#125](https://github.com/rmems/corinth-canal/pull/125) | Unify GGUF/Safetensors family inference (GH#118 PR-1) | 81 | 44 | 29 | +1139/−230, 11 files | 2026-07-23 | #133 |
| [#142](https://github.com/rmems/corinth-canal/pull/142) | Accept dense_sim/stub_uniform in ROUTING_MODE | 33 | 14 | 10 | +139/−23, 3 files | 2026-08-11 | #140 |
| [#138](https://github.com/rmems/corinth-canal/pull/138) | Recover priority-ordered GGUF synapse source selection (GH#118 PR-2) | 11 | 13 | 19 | +891/−143, 6 files | 2026-08-08 | #134 |
| [#128](https://github.com/rmems/corinth-canal/pull/128) | Split checkpoint.rs into private gguf/ modules (GH#118 PR-4) | 9 | 6 | 15 | +1329/−1207, 11 files | 2026-07-21 | — |
| [#127](https://github.com/rmems/corinth-canal/pull/127) | Extract config validation helpers (GH#118 PR-3) | 7 | 2 | 12 | +49/−30, 1 file | 2026-07-22 | #135 |
| [#126](https://github.com/rmems/corinth-canal/pull/126) | Priority-ordered GGUF synapse source selection (GH#118 PR-2) | 6 | 2 | 20 | +597/−130, 3 files | 2026-07-22 | — |

Notes from the 2026-08-18 extract:

- Live `list_merged_prs.py --repo rmems/corinth-canal` confirmed `#125`, `#126`,
  `#127`, `#128`, `#138`, and `#142` as merged PRs of this repo (none excluded at
  provenance). Raw API counts in the table above match the 2026-08-16 scan.
- All six were shortlisted. `#125` and `#142` remain the strongest review→fix
  trajectories (179 and 50 kept). `#138` is the *recovery* of `#126` (same GH#118
  PR-2 label); both are in the JSONL as a regression→repair pair.
- **Skipped (not domain-signal):** [#136](https://github.com/rmems/corinth-canal/pull/136)
  `[ImgBot] Optimize images`; [#139](https://github.com/rmems/corinth-canal/pull/139)
  chore Claude/cloud-agent config; [#130](https://github.com/rmems/corinth-canal/pull/130)
  chore CI runner matrix; [#156](https://github.com/rmems/corinth-canal/pull/156)
  docs retarget of safetensors inspect to engram-parser.
- Still deferred: GH#147 module-extraction series
  ([#152](https://github.com/rmems/corinth-canal/pull/152),
  [#153](https://github.com/rmems/corinth-canal/pull/153),
  [#154](https://github.com/rmems/corinth-canal/pull/154), merged 2026-08-12/13).
  Lower measured density than this wave; re-check for a later extract.
