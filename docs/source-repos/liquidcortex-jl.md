# LiquidCortex.jl

<!-- index: [rmems/LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl) | v0 extracted -->

**Repo**: [rmems/LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl)  
**Description**: Julia liquid-state machine (step plasticity, GPU step options, generic LSM)  
**Language**: Julia  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/liquidcortex-jl-v0.jsonl](../../datasets/jsonl/liquidcortex-jl-v0.jsonl)  
**Metadata card**: [datasets/cards/liquidcortex-jl-v0.json](../../datasets/cards/liquidcortex-jl-v0.json)

> Three domain PRs survived the skip list (Wave A-style shortlist).

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#45](https://github.com/rmems/LiquidCortex.jl/pull/45) | feat: experimental step plasticity + GPU step options | gpu-compute | feature | 56 kept / 8 emitted. |
| [#12](https://github.com/rmems/LiquidCortex.jl/pull/12) | refactor: remove market telemetry, switch to MIT/Apache-2.0 | snn | repair | 32 kept. Closes #7 / #8 / #9. |
| [#33](https://github.com/rmems/LiquidCortex.jl/pull/33) | test: add reference LSM coverage | snn | validation | 4 kept. Closes #22. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #45 | 56 | 8 | 8 | shortlisted |
| #12 | 32 | 8 | 8 | shortlisted |
| #33 | 4 | 4 | 4 | shortlisted |
| #4 | 34 | 8 | 8 | dropped (CI/Codecov/Sentry + rename) |

## Considered and rejected

- **`#4`** — CI/Codecov/Sentry workflows dominate the delta.
- Action bumps, ImgBot, docs, Sentry-only repairs — skip list.
