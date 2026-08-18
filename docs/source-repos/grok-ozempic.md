# grok-ozempic

<!-- index: [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic) | v0 extracted -->

**Repo**: [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic)  
**Description**: SNN-logic ternary quantization for Grok-1 MoE (xai-dissect manifests, GOZ1 packs, SAAQ artifact validation)  
**Language**: Rust (default); Python on `#42` via `language_by_pr`  
**Status**: v0 **extracted** (2026-08-02; **#42 added 2026-08-12**, issue [#20](https://github.com/rmems/operation-prometheus/issues/20)) — see [datasets/jsonl/grok-ozempic-v0.jsonl](../../datasets/jsonl/grok-ozempic-v0.jsonl)  
**Metadata card**: [datasets/cards/grok-ozempic-v0.json](../../datasets/cards/grok-ozempic-v0.json)

> **Shortlist revised 2026-08-02** (issue [#11](https://github.com/rmems/operation-prometheus/issues/11)).
> The original 6-PR list was written before the collector/normalizer existed and before
> ~9 further PRs merged. Re-scored against measured pipeline yield: added `#43` and `#33`,
> dropped `#8`. **`#42` added 2026-08-12** after [#18](https://github.com/rmems/operation-prometheus/issues/18)
> (review-signal dedupe) and [#19](https://github.com/rmems/operation-prometheus/issues/19)
> (`language_by_pr`). See [Measured review-signal yield](#measured-review-signal-yield).

## Shortlisted PRs

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
[`extract_review_signals`](../../scripts/lib/normalize.py) (hard cap `max_items=8`).
`rmems` is the repo's **only human account** — every other login is automation, so most
engineering signal arrives via the `gemini-code-assist` / `chatgpt-codex-connector`
allowlist, which raise the problems the maintainer then patches.

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #11 | 103 | 8 | 8 | shortlisted |
| #33 | 70 | 8 | 8 | **added** |
| #43 | 59 | 8 | 8 | **added** (unique bodies 7→8 after #18 dedupe re-normalize) |
| #24 | 58 | 8 | 8 | shortlisted |
| #29 | 54 | 8 | 8 | shortlisted |
| #42 | 51 | 8 | **8** | **added** 2026-08-12 (#18/#19) — was 1 unique pre-dedupe |
| #26 | 31 | 8 | 8 | shortlisted |
| #25 | 31 | 8 | 8 | shortlisted |
| #8 | 3 | 2 | 2 | **dropped** |

## Deferred, later extracted

- **`#42`** (export Grok-1 embedding pickle → `.npy`) — **extracted 2026-08-12** (issue
  [#20](https://github.com/rmems/operation-prometheus/issues/20)); now in the shortlist above.
  Was deferred because 51 kept signals filled the emit cap (8) with **1 unique**
  `Addressed in <sha>: …` ack body (eight emitted copies of the same ack) and the PR is
  Python against a Rust card. After
  [#18](https://github.com/rmems/operation-prometheus/issues/18) (body dedupe / ack
  deprioritization) and [#19](https://github.com/rmems/operation-prometheus/issues/19)
  (`language_by_pr: {"42": "Python"}`), the record emits **8 unique** review signals and
  `language: Python`.

## Considered and rejected

- **`#8`** (wire manifest into pipeline) — was shortlisted, now dropped. Yields only 2 review
  signals, one of which is `@copilot Make changes to the pull request`. Its phase-1 sibling
  `#7` is no better (2). The pipeline-wiring content is real, but there is no review→patch
  trajectory to learn from.
- **`#54`** (xai-dissect run3 cartography handoff) — adds **164,329 lines** of generated
  export artifacts. Excluded under [data-policy.md](../data-policy.md); it is the concrete case
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
out of curated patches — see [`_NOISE_PATCH_DIRS`](../../scripts/lib/normalize.py).

## Candidate next wave (2026-08-16 scan — not extracted)

The v0 extract stops at `#43`. A GOZ1 v2/v3 + expert-remedy wave (`#69`–`#79`) has
merged since, with heavy Codex/Gemini review→patch traffic. **Raw** GitHub API counts
(`reviews` / review threads / issue comments — *pre* bot-filter; pipeline yield is
measured at extraction time):

| PR | Title | Reviews | Threads | Comments | Size | Merged | Closes |
|----|-------|---------|---------|----------|------|--------|--------|
| [#74](https://github.com/rmems/grok-ozempic/pull/74) | Expert higher-precision remedies for multi-block residual fidelity | 63 | 33 | 10 | +3714/−77, 9 files | 2026-08-08 | #73 |
| [#72](https://github.com/rmems/grok-ozempic/pull/72) | Expert-only ternary multi-block residual fidelity | 54 | 32 | 11 | +2422/−3, 7 files | 2026-08-08 | #68 |
| [#69](https://github.com/rmems/grok-ozempic/pull/69) | GOZ1 v2 persists the per-tensor ternary scale | 40 | 46 | 22 | +1588/−72, 22 files | 2026-08-07 | #65 |
| [#71](https://github.com/rmems/grok-ozempic/pull/71) | GOZ1 v3 persists the applied per-tensor gif_threshold | 25 | 26 | 12 | +817/−121, 10 files | 2026-08-08 | #66 |
| [#76](https://github.com/rmems/grok-ozempic/pull/76) | Measure stacked and denser expert remedies | 18 | 44 | 10 | +9059/−38, 22 files | 2026-08-11 | #75 |
| [#77](https://github.com/rmems/grok-ozempic/pull/77) | Harden co-author hooks (Codex & Muse) + regression tests | 16 | 28 | 9 | +594/−36, 8 files | 2026-08-11 | — |
| [#79](https://github.com/rmems/grok-ozempic/pull/79) | Harden #75 secondary evidence validation (PR #76 bot review) | 6 | 8 | 8 | +193/−24, 5 files | 2026-08-11 | — |

Notes from the scan:

- `#76` → `#79` is a merged review→patch pair (`#79` exists solely to answer `#76`'s
  bot review) — extract together, mirroring the `#78`/`#79` pattern in worktrees-hives.
- Beyond the wave: [#83](https://github.com/rmems/grok-ozempic/pull/83) (INT4 expert
  middle-ground, **112 reviews / 65 threads** — the highest raw review count in the
  repo, merged 2026-08-13) and [#86](https://github.com/rmems/grok-ozempic/pull/86)
  (#85 harness, 37 reviews / 60 threads, merged 2026-08-15) are prime candidates for
  the wave after this one.
- `#76`'s +9059 lines are dominated by measurement artifacts — check the
  [data-policy.md](../data-policy.md) generated-artifact exclusion before extracting.
