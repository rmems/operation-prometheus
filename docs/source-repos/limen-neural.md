# Limen-Neural (organization)

<!-- index: [Limen-Neural](https://github.com/Limen-Neural) (org) | Wave A extracted (axon-encoder) -->

**Org**: [Limen-Neural](https://github.com/Limen-Neural) — public SNN / neuromorphic research stack (owner: rmems).  
**Inventory (2026-07)**: ~23 public repos; ~250–293 merged PRs org-wide; ~15% Dependabot noise.  
**Languages**: Rust-majority (axon-encoder, neuromod, kinetic-signals, limbic-critic, …) + Julia (SpikeStream, TemporalFocus, NeuroPulse, LiquidCortex, …) + SystemVerilog (`silicon-hdl`).  
**Policy**: Extract **public** engineering history only into this forge. Owner access does not mean private repos may be committed here.

## Wave A target repos

| Priority | Repo | Why |
|----------|------|-----|
| 1 | [Limen-Neural/axon-encoder](https://github.com/Limen-Neural/axon-encoder) | Highest useful signal: API, security, review→fix |
| 2 | [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod) | Core SNN models (skip CI-monster bulk PRs) |
| 3 | [SpikeStream.jl](https://github.com/Limen-Neural/SpikeStream.jl) / [kinetic-signals](https://github.com/Limen-Neural/kinetic-signals) | Package boundary + streaming features |
| 4 | [limbic-critic](https://github.com/Limen-Neural/limbic-critic) | Modulator semantics (not REUSE/CHANGELOG-only) |

## axon-encoder — first extract shortlist

**Status**: v0 **extracted** (see card/JSONL)  
**Metadata card**: [datasets/cards/limen-axon-encoder-v0.json](../../datasets/cards/limen-axon-encoder-v0.json)  
**JSONL**: [datasets/jsonl/limen-axon-encoder-v0.jsonl](../../datasets/jsonl/limen-axon-encoder-v0.jsonl)

> **Wave A / v0 exception:** This first Limen extract uses **three** high-signal PRs.
> The usual “at least five” shortlist rule below still applies to new source repos;
> Wave A intentionally ships a smaller pilot so review→fix density can be validated
> before expanding the Limen shortlist.

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#37](https://github.com/Limen-Neural/axon-encoder/pull/37) | feat(modulators): dynamic neuromodulator gain curves | snn, api | review-to-patch | GainCurve + modulated encode paths; strong review→fix (zero-scale, serde). |
| [#50](https://github.com/Limen-Neural/axon-encoder/pull/50) | sec(rng): replace insecure xorshift with rand | security | repair | RNG correctness + seeded determinism tests. |
| [#41](https://github.com/Limen-Neural/axon-encoder/pull/41) | Fix Codacy + standardize encoders | api, ci | review-to-patch | Encoder trait/module move + review hardening. |

## Later waves (pointers only — not extracted)

| Repo | PRs | Notes |
|------|-----|--------|
| neuromod | #5, #8, #9 | Feature then repair/generalize; defer #33 CI monster |
| SpikeStream.jl | #22, #25 | Boundary cut + golden fixtures |
| kinetic-signals | #2, #6, #17 | VolEstimator → Surprise → deprecation |
| limbic-critic | #29, #30 | Dep decoupling + surprise semantics |

Cross-repo exclusion policy lives in [_index.md](_index.md#avoid-for-v0-training).
