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
**Status**: v0 **extracted** (2026-08-02) — see [datasets/jsonl/grok-ozempic-v0.jsonl](../datasets/jsonl/grok-ozempic-v0.jsonl)  
**Metadata card**: [datasets/cards/grok-ozempic-v0.json](../datasets/cards/grok-ozempic-v0.json)

> **Shortlist revised 2026-08-02** (issue [#11](https://github.com/rmems/operation-prometheus/issues/11)).
> The original 6-PR list was written before the collector/normalizer existed and before
> ~9 further PRs merged. Re-scored against measured pipeline yield: added `#43` and `#33`,
> dropped `#8`. See [Measured review-signal yield](#measured-review-signal-yield-grok-ozempic).

### Shortlisted PRs (grok-ozempic)

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#29](https://github.com/rmems/grok-ozempic/pull/29) | Full test coverage, alignment verification, Docker CI | validation, CI | validation | BackendKernel becomes fallible; Local/Myelin parity tests; dry-run alignment guards; Docker + cargo audit. Closes #16, #22, #27. |
| [#26](https://github.com/rmems/grok-ozempic/pull/26) | Align with xai-dissect inventory | validation | validation | 770-tensor inventory + structural manifest; replaces heuristic dry-run counts. Closes #22. |
| [#24](https://github.com/rmems/grok-ozempic/pull/24) | SAAQ artifact validation flow | validation | validation | Multi-step convert/validate ladder with path/symlink hardening. Closes #13–#15, #17–#19. |
| [#25](https://github.com/rmems/grok-ozempic/pull/25) | myelin-accelerator as CUDA backend | ml-infra | feature | CUDA ownership boundary via BackendKernel + DryRunPlanner. Closes #21. |
| [#11](https://github.com/rmems/grok-ozempic/pull/11) | xai-dissect compatible artifact generation | ml-infra | feature | Artifact IR, detector/validator, CLI generate/validate. Closes #10. |
| [#43](https://github.com/rmems/grok-ozempic/pull/43) | quantize-goz1 CLI for GOZ1 run_quantization | ml-infra | review-to-patch | 17 commits; 6 Codex P2 findings (input-format default, env manifest precedence, GIF threshold validation, lossy path conversion) each answered by a patch. Advances #38. |
| [#33](https://github.com/rmems/grok-ozempic/pull/33) | refactor(tests): reduce duplication and complexity | testing | review-to-patch | 51 commits; highest human review density in the repo. Gemini raises helper duplication / semver break, maintainer answers with `Fixed in <sha>` plus explicit rejected-alternative rationale. Advances #28, #20. |

### Measured review-signal yield (grok-ozempic)

Counted by replaying each PR's reviews, review comments, and issue comments through the
pipeline's own [`is_bot_user`](../scripts/lib/bots.py) filter and
[`extract_review_signals`](../scripts/lib/normalize.py) (hard cap `max_items=8`).
`rmems` is the repo's **only human account** — every other login is automation, so most
engineering signal arrives via the `gemini-code-assist` / `chatgpt-codex-connector`
allowlist, which raise the problems the maintainer then patches.

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #11 | 103 | 8 | 8 | shortlisted |
| #33 | 70 | 8 | 8 | **added** |
| #43 | 59 | 8 | 7 | **added** |
| #24 | 58 | 8 | 8 | shortlisted |
| #29 | 54 | 8 | 8 | shortlisted |
| #42 | 51 | 8 | **1** | deferred — see below |
| #26 | 31 | 8 | 8 | shortlisted |
| #25 | 31 | 8 | 8 | shortlisted |
| #8 | 3 | 2 | 2 | **dropped** |

### Considered and rejected

- **`#8`** (wire manifest into pipeline) — was shortlisted, now dropped. Yields only 2 review
  signals, one of which is `@copilot Make changes to the pull request`. Its phase-1 sibling
  `#7` is no better (2). The pipeline-wiring content is real, but there is no review→patch
  trajectory to learn from.
- **`#42`** (export Grok-1 embedding pickle → `.npy`) — **deferred, not rejected.** 51 kept
  signals collapse to 8 byte-identical copies of one `Addressed in <sha>: …` ack, because
  `_BARE_FIXED_IN_REPLY` only drops *bare* fixed-in replies and nothing dedupes repeated
  bodies. It is also Python while the card declares Rust, and `language_for` has no
  `language_by_pr` escape hatch (unlike `domain_by_pr`). Revisit once both are fixed.
- **`#54`** (xai-dissect run3 cartography handoff) — adds **164,329 lines** of generated
  export artifacts. Excluded under [data-policy.md](data-policy.md); it is the concrete case
  that issue #14 (sibling data root) exists to handle.
- **`#46` / `#45`** — agent-config docs. `#46` has the largest raw review volume in the repo
  (176 kept signals) but no domain code delta, so it fails the "pure docs" exclusion.
- **`#55`, `#52`** — open, unmerged. `#55` (V2 structural name bridge) is real `src/core/stream.rs`
  work and worth revisiting once merged.
- **`#44`, `#23`, `#12`** — docs only. **`#1`, `#2`, `#3`, `#4`, `#9`** — early scaffold, 0–2 signals
  (their only reviewers were `greptile-apps`, which the bot filter drops).

Note: the earlier verdict that `#33` was "review-noise heavy … optional secondary only" counted
raw comment volume (168, of which 77 were bot reviews). After the pipeline's filter it is the
cleanest review→fix trajectory in the repo. Only `#11` reaches the 96 KiB patch budget and
carries the `# … truncated …` footer; `#24` (77,970 chars) and `#26` (50,149) are complete.
`#26` is smaller than its raw diff because `.beads/` and `.claude/` agent state is filtered
out of curated patches — see [`_NOISE_PATCH_DIRS`](../scripts/lib/normalize.py).

### Candidate next: myelin-accelerator

[rmems/myelin-accelerator](https://github.com/rmems/myelin-accelerator) is thinner but high
CUDA/SNN fit. Table refreshed 2026-08-02 with measured signal counts:

| PR | Kept signals | Notes |
|----|--------------|-------|
| [#26](https://github.com/rmems/myelin-accelerator/pull/26) | 50 | Packed ternary GEMV/GEMM kernels + CUDA 13.3.1 CI (+2653/−111, 36 files). Best overall. |
| [#18](https://github.com/rmems/myelin-accelerator/pull/18) | 53 | Bitpacking + GPU CI + 62 tests + benches |
| [#22](https://github.com/rmems/myelin-accelerator/pull/22) | 22 | CUDA quality gate — **now merged** (was listed as "watch") |
| [#7](https://github.com/rmems/myelin-accelerator/pull/7) | 25 | Corinth Canal CUDA/cust review→patch hardening |
| [#6](https://github.com/rmems/myelin-accelerator/pull/6) | 13 | Feature-gated CUDA precursor to #7 |

Dropped from the previous list: `#4` (0 kept signals) and `#2` (3 signals across 648 mostly
`target/` files).

---

## Limen-Neural (organization)

**Org**: [Limen-Neural](https://github.com/Limen-Neural) — public SNN / neuromorphic research stack (owner: rmems).  
**Inventory (2026-07)**: ~23 public repos; ~250–293 merged PRs org-wide; ~15% Dependabot noise.  
**Languages**: Rust-majority (axon-encoder, neuromod, kinetic-signals, limbic-critic, …) + Julia (SpikeStream, TemporalFocus, NeuroPulse, LiquidCortex, …) + SystemVerilog (`silicon-hdl`).  
**Policy**: Extract **public** engineering history only into this forge. Owner access does not mean private repos may be committed here.

### Wave A target repos

| Priority | Repo | Why |
|----------|------|-----|
| 1 | [Limen-Neural/axon-encoder](https://github.com/Limen-Neural/axon-encoder) | Highest useful signal: API, security, review→fix |
| 2 | [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod) | Core SNN models (skip CI-monster bulk PRs) |
| 3 | [SpikeStream.jl](https://github.com/Limen-Neural/SpikeStream.jl) / [kinetic-signals](https://github.com/Limen-Neural/kinetic-signals) | Package boundary + streaming features |
| 4 | [limbic-critic](https://github.com/Limen-Neural/limbic-critic) | Modulator semantics (not REUSE/CHANGELOG-only) |

### axon-encoder — first extract shortlist

**Status**: v0 **extracted** (see card/JSONL)  
**Metadata card**: [datasets/cards/limen-axon-encoder-v0.json](../datasets/cards/limen-axon-encoder-v0.json)  
**JSONL**: [datasets/jsonl/limen-axon-encoder-v0.jsonl](../datasets/jsonl/limen-axon-encoder-v0.jsonl)

> **Wave A / v0 exception:** This first Limen extract uses **three** high-signal PRs.
> The usual “at least five” shortlist rule below still applies to new source repos;
> Wave A intentionally ships a smaller pilot so review→fix density can be validated
> before expanding the Limen shortlist.

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#37](https://github.com/Limen-Neural/axon-encoder/pull/37) | feat(modulators): dynamic neuromodulator gain curves | snn, api | review-to-patch | GainCurve + modulated encode paths; strong review→fix (zero-scale, serde). |
| [#50](https://github.com/Limen-Neural/axon-encoder/pull/50) | sec(rng): replace insecure xorshift with rand | security | repair | RNG correctness + seeded determinism tests. |
| [#41](https://github.com/Limen-Neural/axon-encoder/pull/41) | Fix Codacy + standardize encoders | api, ci | review-to-patch | Encoder trait/module move + review hardening. |

### Later waves (pointers only — not extracted)

| Repo | PRs | Notes |
|------|-----|--------|
| neuromod | #5, #8, #9 | Feature then repair/generalize; defer #33 CI monster |
| SpikeStream.jl | #22, #25 | Boundary cut + golden fixtures |
| kinetic-signals | #2, #6, #17 | VolEstimator → Surprise → deprecation |
| limbic-critic | #29, #30 | Dep decoupling + surprise semantics |

### Avoid for v0 training

- Dependabot / Renovate dependency-only merges  
- REUSE / CHANGELOG / publish-prep only  
- Pure docs (Sentry guides, cloud AGENTS notes) without code delta  
- Bulk CI modernization multi-issue monsters without domain signal  

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
