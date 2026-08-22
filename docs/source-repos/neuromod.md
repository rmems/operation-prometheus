# neuromod

<!-- index: [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod) | v0 extracted -->

**Repo**: [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod)  
**Description**: Core SNN models and neuromodulator API (LIF/HH/FHN/Hebbian, domain-agnostic modulators)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#28](https://github.com/rmems/operation-prometheus/issues/28), Limen Wave B+ pilot) — see [datasets/jsonl/neuromod-v0.jsonl](../../datasets/jsonl/neuromod-v0.jsonl)  
**Metadata card**: [datasets/cards/neuromod-v0.json](../../datasets/cards/neuromod-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#5](https://github.com/Limen-Neural/neuromod/pull/5) | feat: add Lapicque, Hodgkin-Huxley, FitzHugh-Nagumo, and Hebbian neuron models | snn | feature | 4 unique kept; new biophysical modules. Body names issue #3 (no close keyword). |
| [#8](https://github.com/Limen-Neural/neuromod/pull/8) | Fix bench warnings | snn | bug-prediction | 2 unique; HH rewrite + standalone crate (not a warning-only chore). Both retained reviews (voltage-convention mismatch, hard-coded reset state) still describe defects present in the merged patch. |
| [#9](https://github.com/Limen-Neural/neuromod/pull/9) | Generalize neuromod core: dynamic dimensions, neutral API, and trait purge | api | bug-prediction | 2 unique; dimension-configurable `SpikingNetwork`. Retained P1 review flags the zero-init weights change the merged patch itself introduces — no later fix commit captured, so this is a flagged-bug trajectory, not review-to-patch. |
| [#2](https://github.com/Limen-Neural/neuromod/pull/2) | SNN Core: Mining & HFT Purge | snn | review-to-patch | 7 unique; strips blockchain/HFT from the engine. |
| [#15](https://github.com/Limen-Neural/neuromod/pull/15) | refactor: domain-agnostic neuromodulator API and CI workflow | ml-infra | review-to-patch | 8 unique; Closes #13/#14. Domain API plus a CI workflow — not a bulk-CI monster. |

## PR Details

### PR #5 — feat: add Lapicque, Hodgkin-Huxley, FitzHugh-Nagumo, and Hebbian neuron models

- **URL**: https://github.com/Limen-Neural/neuromod/pull/5
- **Merged**: 2026-04-04
- **Files changed**: 8
- **Why high-signal**: Adds the four foundational neuron models requested in issue #3 (`lapicque`, `hodgkin_huxley`, `fitzhugh_nagumo`, classical Hebbian STDP).
- **Dataset bucket**: `feature`
- **Provenance**: Limen-Neural/neuromod#3 (card `linked_issues_by_pr`; body has no close keyword)

### PR #8 — Fix bench warnings

- **URL**: https://github.com/Limen-Neural/neuromod/pull/8
- **Merged**: 2026-04-22
- **Files changed**: 5
- **Why high-signal**: Title is “Fix bench warnings”; the delta rewrites Hodgkin-Huxley rest/reset behavior and detaches workspace-only deps. Card `task_type_by_pr` is `refactor`.
- **Dataset bucket**: `bug-prediction` (both retained reviews -- absolute-vs-relative voltage convention in `new_cortical()`, hard-coded `reset()` state -- still describe defects present in the merged patch; no corrective follow-up is captured in this extract)

### PR #9 — Generalize neuromod core: dynamic dimensions, neutral API, and trait purge

- **URL**: https://github.com/Limen-Neural/neuromod/pull/9
- **Merged**: 2026-04-22
- **Files changed**: 10
- **Why high-signal**: Makes `SpikingNetwork` dimension-configurable and removes domain-specific topology bootstrapping.
- **Dataset bucket**: `bug-prediction` (retained P1 review flags the zero-init weights change this same patch introduces; no corrective follow-up commit is captured in this extract)

### PR #2 — SNN Core: Mining & HFT Purge

- **URL**: https://github.com/Limen-Neural/neuromod/pull/2
- **Merged**: 2026-04-04
- **Files changed**: 9
- **Why high-signal**: Deletes mining/HFT paths so the crate is a pure neuromorphic primitive library.
- **Dataset bucket**: `review-to-patch`

### PR #15 — refactor: domain-agnostic neuromodulator API and CI workflow

- **URL**: https://github.com/Limen-Neural/neuromod/pull/15
- **Merged**: 2026-06-21
- **Files changed**: 25
- **Why high-signal**: Aligns `NeuroModulators` with generic dopamine/serotonin/acetylcholine/norepinephrine names (`GenericReward`, `SignalProfile`). Also adds CI for #14; 21 of 25 files are Rust domain code.
- **Dataset bucket**: `review-to-patch`
- **Closes**: Limen-Neural/neuromod#13, #14

## Measured review density (raw, 2026-08-20)

| PR | Reviews | Threads | Yield (unique) | Size | Verdict |
|----|---------|---------|----------------|------|---------|
| #15 | 10 | 12 | 8 | +1079/−560, 25 files | shortlisted |
| #2 | 8 | 17 | 7 | +96/−187, 9 files | shortlisted |
| #5 | 5 | 10 | 4 | +939/−30, 8 files | shortlisted |
| #9 | 7 | 12 | 2 | +258/−269, 10 files | shortlisted (issue smoke) |
| #8 | 3 | 6 | 2 | +378/−210, 5 files | shortlisted (issue smoke) |
| #1 | 1 | 4 | 0 | +5/−5 | skipped (zero yield) |

## Deferred (not rejected)

- **`#96`–`#98`** — release/Docker-CI review chain; high raw reviews, low domain signal.
- **`#33`** — bulk CI modernization monster (`feat(ci): large modernization PR`).

## Considered and rejected

- Dependabot / actions group bumps (`#100`, `#99`, `#87`, …)
- Docs-only packaging and wiki sync (`#84`, `#93`, `#63`)
