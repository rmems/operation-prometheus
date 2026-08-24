# kinetic-signals

<!-- index: [rmems/kinetic-signals](https://github.com/rmems/kinetic-signals) | v0 extracted -->

**Repo**: [rmems/kinetic-signals](https://github.com/rmems/kinetic-signals)  
**Description**: Streaming signal-processing crate (Hawkes/surprise/stats) at the SpikeStream.jl language boundary  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#28](https://github.com/rmems/operation-prometheus/issues/28), Limen Wave B+ pilot) — see [datasets/jsonl/kinetic-signals-v0.jsonl](../../datasets/jsonl/kinetic-signals-v0.jsonl)  
**Metadata card**: [datasets/cards/kinetic-signals-v0.json](../../datasets/cards/kinetic-signals-v0.json)

> Org drift: transferred **Limen-Neural → rmems**. Counts below are **raw** GitHub
> API totals (*pre* bot-filter). Pipeline yield is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#39](https://github.com/rmems/kinetic-signals/pull/39) | test: expand shared_vectors for streaming APIs (LIM-201, #28) | telemetry | validation | Densest Wave B candidate: 109 raw reviews / 8 unique kept. |
| [#35](https://github.com/rmems/kinetic-signals/pull/35) | test: expand demo for missing APIs (LIM-199, #26) | telemetry | validation | 6 unique; streaming Hawkes + surprise demo coverage. |
| [#17](https://github.com/rmems/kinetic-signals/pull/17) | refactor!: remove deprecated GBM aliases, bump to v0.4.0 | snn | repair | 3 unique (a duplicate fix confirmation and two orphan replies with no preserved originating comment were dropped); Closes #15. |
| [#6](https://github.com/rmems/kinetic-signals/pull/6) | Dev environment setup + resolve open issues (#3, #4, #5) | infra | feature | 3 unique (five orphan replies about CI hardening/fixture params with no preserved originating comment were dropped); #4 domain rename plus CI for #5 — kept for the domain half. |
| [#1](https://github.com/rmems/kinetic-signals/pull/1) | Generalizing | ml-infra | bug-prediction | 1 unique; strips third-party deps and serde gates. Retained P1 review flags the NaN-dropping clamp the patch itself introduces — no corrective commit captured, so this is bug-prediction, not a clean feature trajectory. |

## PR Details

### PR #39 — test: expand shared_vectors for streaming APIs

- **URL**: https://github.com/rmems/kinetic-signals/pull/39
- **Merged**: 2026-07-29
- **Commits**: 29
- **Files changed**: 10
- **Why high-signal**: Golden fixtures for streaming Hawkes, surprise sequences, and signal stats after SpikeStream.jl dropped those proxies.
- **Dataset bucket**: `validation`
- **Provenance**: kinetic-signals#28 (card `linked_issues_by_pr`; title names `#28` without a close keyword)

### PR #35 — test: expand demo for missing APIs

- **URL**: https://github.com/rmems/kinetic-signals/pull/35
- **Merged**: 2026-07-23
- **Files changed**: 1 (`examples/demo.rs`)
- **Why high-signal**: Demo coverage for streaming Hawkes, surprise+anomaly, stats, EMA/SMA/ZScore.
- **Dataset bucket**: `validation`
- **Provenance**: kinetic-signals#26 (card)

### PR #17 — refactor!: remove deprecated GBM aliases

- **URL**: https://github.com/rmems/kinetic-signals/pull/17
- **Merged**: 2026-07-04
- **Files changed**: 6
- **Why high-signal**: Deletes `src/gbm.rs` aliases and the deprecated-alias test file. Closes #15.
- **Dataset bucket**: `repair`

### PR #6 — Dev environment setup + resolve open issues (#3, #4, #5)

- **URL**: https://github.com/rmems/kinetic-signals/pull/6
- **Merged**: 2026-06-21
- **Files changed**: 15
- **Why high-signal**: Mixed env/CI + domain rename (`#4`). Card domain `infra`; task_type `refactor`.
- **Dataset bucket**: `feature`
- **Provenance**: issues #3, #4, #5 (`#4`/`#5` via close keywords; `#3` via card `linked_issues_by_pr` -- body says "refs #3", not a close keyword)

### PR #1 — Generalizing

- **URL**: https://github.com/rmems/kinetic-signals/pull/1
- **Merged**: 2026-04-19
- **Files changed**: 12
- **Why high-signal**: Local `real.rs` trait replaces num-traits; removes serde-gated derives.
- **Dataset bucket**: `bug-prediction` (retained P1 review flags the `h.max(T::zero()).min(T::one())` clamp this same patch introduces as NaN-dropping; no corrective follow-up commit is captured in this extract)

## Measured review density (raw, 2026-08-20)

| PR | Reviews | Threads | Yield (unique) | Size | Verdict |
|----|---------|---------|----------------|------|---------|
| #39 | 109 | 98 | 8 | +1411/−92, 10 files | shortlisted |
| #6 | 19 | 23 | 8 | +546/−166, 15 files | shortlisted |
| #35 | 7 | 6 | 6 | +149/−4, 1 file | shortlisted |
| #17 | 7 | 8 | 6 | +14/−126, 6 files | shortlisted |
| #1 | 5 | 5 | 1 | +275/−130, 12 files | shortlisted |
| #37 | 1 | 0 | 0 | +219/−0 | skipped (zero yield) |
| #2 | 1 | 1 | 0 | +83/−87 | skipped (zero yield) |

## Deferred (not rejected)

- **`#37`** — unit tests on public APIs but 0 kept review signals after bot filter.
- **`#2`** — VolEstimator salvage; 0 kept signals.

## Considered and rejected

- Docs-only (`#38`, `#34`, `#33`, `#31`, `#19`, `#16`)
- `#42` post-transfer hygiene
- `#29` CI-only MSRV/audit
