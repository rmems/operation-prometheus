# grok-ozempic

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

## Considered and rejected

- **`#8`** (wire manifest into pipeline) — was shortlisted, now dropped. Yields only 2 review
  signals, one of which is `@copilot Make changes to the pull request`. Its phase-1 sibling
  `#7` is no better (2). The pipeline-wiring content is real, but there is no review→patch
  trajectory to learn from.
- **`#42`** (export Grok-1 embedding pickle → `.npy`) — **extracted 2026-08-12** (issue
  [#20](https://github.com/rmems/operation-prometheus/issues/20)). Was deferred because 51 kept
  signals filled the emit cap (8) with **1 unique** `Addressed in <sha>: …` ack body (eight
  emitted copies of the same ack) and the PR is Python against a Rust card. After
  [#18](https://github.com/rmems/operation-prometheus/issues/18) (body dedupe / ack
  deprioritization) and [#19](https://github.com/rmems/operation-prometheus/issues/19)
  (`language_by_pr: {"42": "Python"}`), the record emits **8 unique** review signals and
  `language: Python`.
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
