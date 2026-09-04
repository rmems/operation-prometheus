# limbic-critic

<!-- index: [rmems/limbic-critic](https://github.com/rmems/limbic-critic) | v0 extracted -->

**Repo**: [rmems/limbic-critic](https://github.com/rmems/limbic-critic)  
**Description**: Neuromodulatory RL critic (surprise / acetylcholine, local ModulatorVector)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/limbic-critic-v0.jsonl](../../datasets/jsonl/limbic-critic-v0.jsonl)  
**Metadata card**: [datasets/cards/limbic-critic-v0.json](../../datasets/cards/limbic-critic-v0.json)

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#30](https://github.com/rmems/limbic-critic/pull/30) | Replace SimpleCritic acetylcholine placeholder | snn | feature | 7 kept. Environment-provided surprise instead of hardcoded 0.5. |
| [#29](https://github.com/rmems/limbic-critic/pull/29) | Refactor: Replace neuromod::NeuroModulators with local ModulatorVector | api | repair | 3 kept. Zero sibling Cargo deps. |
| [#2](https://github.com/rmems/limbic-critic/pull/2) | feat: Refactor spikenaut-reward into limbic-critic | snn | repair | 3 kept. Crate rename + generalized critic. |
| [#3](https://github.com/rmems/limbic-critic/pull/3) | Updating crate to fit nre modular crate goals | api | repair | 1 kept. Drop conflicting local NeuroModulators. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #30 | 7 | 7 | 7 | shortlisted |
| #29 | 3 | 3 | 3 | shortlisted |
| #2 | 3 | 3 | 3 | shortlisted |
| #3 | 1 | 1 | 1 | shortlisted (modular crate follow-on) |
| #1 | 0 | 0 | 0 | dropped (0 yield) |

## Considered and rejected

- **`#1`** — homeostasis bootstrap, 0 kept signals.
- **`#36`, `#35`, `#34`, `#33`, `#32`, `#6`, `#31`, `#28`, `#11`** — docs, REUSE, CHANGELOG, publish-prep, CI.
