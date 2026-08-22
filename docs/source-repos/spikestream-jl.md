# SpikeStream.jl

<!-- index: [rmems/SpikeStream.jl](https://github.com/rmems/SpikeStream.jl) | v0 extracted -->

**Repo**: [rmems/SpikeStream.jl](https://github.com/rmems/SpikeStream.jl)  
**Description**: Julia spike-stream feature extraction package (counts, ISI, bursts) at the kinetic-signals boundary  
**Language**: Julia  
**Status**: v0 **extracted** (2026-08-20, issue [#28](https://github.com/rmems/operation-prometheus/issues/28), Limen Wave B+ pilot) — see [datasets/jsonl/spikestream-jl-v0.jsonl](../../datasets/jsonl/spikestream-jl-v0.jsonl)  
**Metadata card**: [datasets/cards/spikestream-jl-v0.json](../../datasets/cards/spikestream-jl-v0.json)

> Org drift: transferred **Limen-Neural → rmems**. Raw review counts on `#18`/`#20`
> out-measure the extracted PRs; those diffs are CI/docs-only and fail the
> [avoid-for-v0-training](_index.md#avoid-for-v0-training) screen.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#7](https://github.com/rmems/SpikeStream.jl/pull/7) | Re-scope SpikeStream around spike-stream feature extraction | snn | feature | 8 unique; adds `spike_features.jl`. |
| [#25](https://github.com/rmems/SpikeStream.jl/pull/25) | test(fixtures): frozen spike feature fixtures and range checks (LIM-41) | snn | validation | 4 unique; Closes #5. |
| [#22](https://github.com/rmems/SpikeStream.jl/pull/22) | chore(api): remove transitional Hurst/Hawkes/GBM compute_ functions (LIM-47) | api | repair | 0 unique (3 raw signals dropped as contextless — no path/line/quoted-text referent); boundary cut vs kinetic-signals. |
| [#21](https://github.com/rmems/SpikeStream.jl/pull/21) | chore: Add streaming benchmarks (#15) | tools | validation | 2 unique (6 of 8 raw signals were author "Acknowledged"/"Addressed" responses with no preserved originating comment); Closes #15. Card `task_type` is `test`. |

## PR Details

### PR #7 — Re-scope SpikeStream around spike-stream feature extraction

- **URL**: https://github.com/rmems/SpikeStream.jl/pull/7
- **Merged**: 2026-05-19
- **Commits**: 10
- **Files changed**: 8
- **Why high-signal**: Introduces first-class spike-event primitives (counts, density, ISI, bursts, windowed/normalized vectors) and keeps market helpers as transitional APIs.
- **Dataset bucket**: `feature`

### PR #25 — test(fixtures): frozen spike feature fixtures and range checks

- **URL**: https://github.com/rmems/SpikeStream.jl/pull/25
- **Merged**: 2026-07-23
- **Files changed**: 6
- **Why high-signal**: Frozen `spike_vectors.json` goldens + range invariants after the kinetic-signals split. Closes #5.
- **Dataset bucket**: `validation`

### PR #22 — chore(api): remove transitional Hurst/Hawkes/GBM compute_ functions

- **URL**: https://github.com/rmems/SpikeStream.jl/pull/22
- **Merged**: 2026-07-22
- **Files changed**: 8
- **Why high-signal**: Deletes `hurst.jl` / `hawkes.jl` / `gbm_surprise.jl` once kinetic-signals owns those proxies. Card `task_type` is `refactor` (beats `chore:`).
- **Dataset bucket**: `repair`

### PR #21 — chore: Add streaming benchmarks (#15)

- **URL**: https://github.com/rmems/SpikeStream.jl/pull/21
- **Merged**: 2026-07-07
- **Files changed**: 2
- **Why high-signal**: BenchmarkTools harness for the six core extractors at three scales. Closes #15.
- **Dataset bucket**: `validation`

## Measured review density (raw, 2026-08-20)

| PR | Reviews | Threads | Raw yield (unique, pre-quality-filter) | Size | Verdict |
|----|---------|---------|----------------|------|---------|
| #18 | 27 | 34 | 8 | +79/−151, CI/docs only | **rejected** (bulk CI) |
| #21 | 26 | 32 | 8 | +75/−0, benches | shortlisted |
| #20 | 21 | 21 | 8 | AGENTS/REVIEW docs | **rejected** (docs) |
| #7 | 12 | 24 | 8 | +481/−110 | shortlisted |
| #25 | 6 | 8 | 4 | +381/−5 | shortlisted |
| #22 | 5 | 2 | 3 | +24/−134 | shortlisted |
| #2 | 2 | 3 | 0 | language scrub | skipped (zero yield) |

## Considered and rejected

- **`#18`** (chore(ci): Upgrade CI workflows + add Codecov) — highest raw review count; no `.jl` domain files.
- **`#20`** (docs: Add AGENTS.md and REVIEW.md) — docs-only.
- **`#24`/`#23`** — boundary/AGENTS docs.
- **`#16`** — license-only.
