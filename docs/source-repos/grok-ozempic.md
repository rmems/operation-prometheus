# grok-ozempic

<!-- index: [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic) | v0 + v1 extracted -->

**Repo**: [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic)  
**Description**: SNN-logic ternary quantization for Grok-1 MoE (xai-dissect manifests, GOZ1 packs, SAAQ artifact validation)  
**Language**: Rust (default); Python on `#42`, `#72`, `#74` via `language_by_pr`  
**Status**: v0 **extracted** (2026-08-02; **#42 added 2026-08-12**) and v1 **extracted** (2026-08-18, issue [#32](https://github.com/rmems/operation-prometheus/issues/32)) — see [grok-ozempic-v0.jsonl](../../datasets/jsonl/grok-ozempic-v0.jsonl) and [grok-ozempic-v1.jsonl](../../datasets/jsonl/grok-ozempic-v1.jsonl)  
**Metadata cards**: [grok-ozempic-v0.json](../../datasets/cards/grok-ozempic-v0.json), [grok-ozempic-v1.json](../../datasets/cards/grok-ozempic-v1.json)

> **v1 shortlist (2026-08-18).** Live `list_merged_prs.py --repo rmems/grok-ozempic` confirmed
> candidates `#69`, `#71`, `#72`, `#74`, `#76`, `#77`, `#79`, `#42` as merged PRs of this repo
> (none excluded at provenance). Scored with Phase 1 `extract_review_signals` dedupe.
> Added `#69`/`#71`/`#72`/`#74`; re-included `#42` (Python). Dropped `#76`/`#77`/`#79`.
> v0 is unchanged.

> **Shortlist revised 2026-08-02** (issue [#11](https://github.com/rmems/operation-prometheus/issues/11)).
> The original 6-PR list was written before the collector/normalizer existed and before
> ~9 further PRs merged. Re-scored against measured pipeline yield: added `#43` and `#33`,
> dropped `#8`. **`#42` added 2026-08-12** after [#18](https://github.com/rmems/operation-prometheus/issues/18)
> (review-signal dedupe) and [#19](https://github.com/rmems/operation-prometheus/issues/19)
> (`language_by_pr`). See [Measured review-signal yield](#measured-review-signal-yield).

## Shortlisted PRs (v1)

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#69](https://github.com/rmems/grok-ozempic/pull/69) | GOZ1 v2 persists the per-tensor ternary scale | quantization | feature | Format bump so `w ≈ α·t` is recoverable from the pack (closes #65). Rust `weight_pack` / `stream` plus route-preservation Python. 27 kept / 8 unique after dedupe. |
| [#71](https://github.com/rmems/grok-ozempic/pull/71) | GOZ1 v3 persists the applied per-tensor gif_threshold | quantization | feature | Per-tensor τ / `threshold_abs` on the row (closes #66). Composes with #69. 14 kept / 8 unique. |
| [#72](https://github.com/rmems/grok-ozempic/pull/72) | Expert-only ternary multi-block residual fidelity | quantization | review-to-patch | **Python.** Sequential 0→3 expert-only GOZ1 v3 experiment (advances #68). Maintainer answers Cubic/Greptile findings with pack-only scale / FP16-control / version-guard patches. 36 kept / 8 unique. |
| [#74](https://github.com/rmems/grok-ozempic/pull/74) | Expert higher-precision remedies for multi-block residual fidelity | quantization | review-to-patch | **Python.** Periodic-HP and channel-α arms on the #72 harness (closes #73). Review findings (`hp_period`, `#72` settings gate, pack SHA identity) each answered by a patch. 37 kept / 8 unique. |
| [#42](https://github.com/rmems/grok-ozempic/pull/42) | export Grok-1 embedding pickle → `.npy` | ml-infra | review-to-patch | **Python** (`language_by_pr`). Re-included in v1 so the non-Rust path is represented in both extracts. Codex P1/P2 findings answered by patches. Advances #37 / RM-189. |

## Shortlisted PRs (v0)

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#29](https://github.com/rmems/grok-ozempic/pull/29) | Full test coverage, alignment verification, Docker CI | validation | validation | BackendKernel becomes fallible; Local/Myelin parity tests; dry-run alignment guards; Docker + cargo audit. References #16, #22, #27. |
| [#26](https://github.com/rmems/grok-ozempic/pull/26) | Align with xai-dissect inventory | validation | validation | 770-tensor inventory + structural manifest; replaces heuristic dry-run counts. References #22. |
| [#24](https://github.com/rmems/grok-ozempic/pull/24) | SAAQ artifact validation flow | validation | validation | Multi-step convert/validate ladder with path/symlink hardening. Closes #13–#15, #17–#19. |
| [#25](https://github.com/rmems/grok-ozempic/pull/25) | myelin-accelerator as CUDA backend | ml-infra | feature | CUDA ownership boundary via BackendKernel + DryRunPlanner. Closes #21. |
| [#11](https://github.com/rmems/grok-ozempic/pull/11) | xai-dissect compatible artifact generation | ml-infra | feature | Artifact IR, detector/validator, CLI generate/validate. Closes #10. |
| [#43](https://github.com/rmems/grok-ozempic/pull/43) | quantize-goz1 CLI for GOZ1 run_quantization | ml-infra | review-to-patch | 17 commits; 6 Codex P2 findings (input-format default, env manifest precedence, GIF threshold validation, lossy path conversion) each answered by a patch. Advances #38. |
| [#33](https://github.com/rmems/grok-ozempic/pull/33) | refactor(tests): reduce duplication and complexity | testing | review-to-patch | 51 commits; highest filtered review-signal density in the repo. Gemini raises helper duplication / semver break, maintainer answers with `Fixed in <sha>` plus explicit rejected-alternative rationale. Advances #28, #20. |
| [#42](https://github.com/rmems/grok-ozempic/pull/42) | export Grok-1 embedding pickle → `.npy` | ml-infra | review-to-patch | **Python** (`language_by_pr`). 17 commits; Codex P1/P2 findings (negative offsets, mmap release, empty shape, stem requirements, restricted umask, privilege pin) each answered by a patch. First non-Rust record in the set. Advances #37 / RM-189. |

## Measured review-signal yield

Counted by replaying each PR's reviews, review comments, and issue comments through the
pipeline's own [`is_bot_user`](../../scripts/lib/bots.py) filter and
[`extract_review_signals`](../../scripts/lib/normalize.py) (hard cap `max_items=8`, SHA-masked
body dedupe from [#18](https://github.com/rmems/operation-prometheus/issues/18)).
`rmems` is the repo's **only human account** — every other login is automation, so most
engineering signal arrives via the `gemini-code-assist` / `chatgpt-codex-connector`
allowlist, which raise the problems the maintainer then patches.

v1 candidates were re-measured from live raw records collected 2026-08-18. Unique-body
counts are post-dedupe (`max_items` therefore counts distinct signals, not SHA-only ack repeats).

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #11 | 103 | 8 | 8 | shortlisted (v0) |
| #33 | 70 | 8 | 8 | **added** (v0) |
| #43 | 59 | 8 | 8 | **added** (v0; unique bodies 7→8 after #18 dedupe re-normalize) |
| #24 | 58 | 8 | 8 | shortlisted (v0) |
| #29 | 54 | 8 | 8 | shortlisted (v0) |
| #42 | 51 | 8 | **8** | **v0** 2026-08-12; **v1** 2026-08-18 — was 1 unique pre-dedupe |
| #74 | 37 | 8 | 8 | **added** (v1) |
| #72 | 36 | 8 | 8 | **added** (v1) |
| #26 | 31 | 8 | 8 | shortlisted (v0) |
| #25 | 31 | 8 | 8 | shortlisted (v0) |
| #69 | 27 | 8 | 8 | **added** (v1) |
| #71 | 14 | 8 | 8 | **added** (v1) |
| #8 | 3 | 2 | 2 | **dropped** (v0) |
| #76 | 2 | 2 | 2 | **dropped** (v1) |
| #77 | 0 | 0 | 0 | **dropped** (v1) |
| #79 | 0 | 0 | 0 | **dropped** (v1) |

## Deferred, later extracted

- **`#42`** (export Grok-1 embedding pickle → `.npy`) — **extracted 2026-08-12** into v0
  (issue [#20](https://github.com/rmems/operation-prometheus/issues/20)); **re-included in v1**
  2026-08-18. Was deferred because 51 kept signals filled the emit cap (8) with **1 unique**
  `Addressed in <sha>: …` ack body (eight emitted copies of the same ack) and the PR is
  Python against a Rust card. After
  [#18](https://github.com/rmems/operation-prometheus/issues/18) (body dedupe / ack
  deprioritization) and [#19](https://github.com/rmems/operation-prometheus/issues/19)
  (`language_by_pr: {"42": "Python"}`), the record emits **8 unique** review signals and
  `language: Python`.

## Considered and rejected

- **`#76`** (measure stacked and denser expert remedies) — live-confirmed merged, but only
  **2 unique** signals after the bot filter, and `+9059` lines are dominated by generated
  `reports/…/metrics.json` payloads. Excluded under [data-policy.md](../data-policy.md)
  generated-artifact guidance plus the yield rule of thumb.
- **`#77`** (harden co-author hooks) — live-confirmed merged; **0** kept signals. Shell/awk
  hook chore with no surviving review→patch trajectory.
- **`#79`** (harden #75 secondary evidence validation) — live-confirmed merged follow-up to
  `#76`'s bot review, but **0** kept signals after `is_bot_user` (the review-to-patch pair
  does not survive the pipeline filter). Dropped with `#76`.
- **`#8`** (wire manifest into pipeline) — was shortlisted, now dropped. Yields only 2 review
  signals, one of which is `@copilot Make changes to the pull request`. Its phase-1 sibling
  `#7` is no better (2). The pipeline-wiring content is real, but there is no review→patch
  trajectory to learn from.
- **`#54`** (xai-dissect run3 cartography handoff) — adds **164,329 lines** of generated
  export artifacts. Excluded under [data-policy.md](../data-policy.md); it is the concrete case
  that issue #14 (sibling data root) exists to handle.
- **`#46` / `#45`** — agent-config docs. `#46` has the largest raw review volume in the repo
  (176 kept signals) but no domain code delta, so it fails the "pure docs" exclusion.
- **`#55`, `#52`** — previously open; `#55` later merged (V2 structural name bridge) but was
  not in the v1 candidate list. Worth a later wave.
- **`#44`, `#23`, `#12`** — docs only. **`#1`, `#2`, `#3`, `#4`, `#9`** — early scaffold, 0–2 signals
  (their only reviewers were `greptile-apps`, which the bot filter drops).

Note: the earlier verdict that `#33` was "review-noise heavy … optional secondary only" counted
raw comment volume (168, of which 77 were bot reviews). After the pipeline's filter it is the
cleanest review→fix trajectory in the repo. Only `#11` reaches the 96 KiB patch budget and
carries the `# … truncated …` footer; `#24` (77,970 chars) and `#26` (50,149) are complete.
`#26` is smaller than its raw diff because `.beads/` and `.claude/` agent state is filtered
out of curated patches — see [`_NOISE_PATCH_DIRS`](../../scripts/lib/normalize.py).
v1 `#69` also hits the 96 KiB budget (`patch_chars` 96,234).

## Later waves (not extracted)

The v1 extract stops at the GOZ1 v2/v3 + expert-remedy cluster (`#69`–`#74` plus `#42`).
Beyond that wave, still unextracted:

| PR | Title | Notes |
|----|-------|-------|
| [#83](https://github.com/rmems/grok-ozempic/pull/83) | INT4 expert middle-ground | Highest raw review count in the repo (merged 2026-08-13) |
| [#86](https://github.com/rmems/grok-ozempic/pull/86) | #85 harness — stacked INT4 + LS channel-α | Merged 2026-08-15 |

`#76` → `#79` was considered as a review→patch pair (mirroring worktrees-hives `#78`/`#79`)
and rejected on measured yield; see [Considered and rejected](#considered-and-rejected).
