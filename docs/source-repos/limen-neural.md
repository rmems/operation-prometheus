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

> Refreshed from a live scan 2026-08-16 (issue #28 wave B). Review counts are **raw**
> GitHub API `reviews` totals (pre bot-filter). **Org drift**: `SpikeStream.jl`,
> `kinetic-signals`, and `limbic-critic` have been **transferred Limen-Neural → rmems**
> (see kinetic-signals#42 "post-transfer hygiene") — links below point at rmems.

| Repo | Candidate PRs | Notes |
|------|---------------|--------|
| [neuromod](https://github.com/Limen-Neural/neuromod) | #5, #8, #9; newer #97 (23 rev), #96 (42 rev), #98 (15 rev) | Repo now past #99. Feature then repair/generalize; defer #33 CI monster; #96–#98 are a release/Docker-CI review chain |
| [SpikeStream.jl](https://github.com/rmems/SpikeStream.jl) | #22, #25; higher-signal #18 (27 rev), #21 (26 rev), #20 (21 rev) | **Now rmems.** Boundary cut + golden fixtures; #18/#21 out-measure the original pointers |
| [kinetic-signals](https://github.com/rmems/kinetic-signals) | #2, #6, #17; newer #39 (**109 rev / 49 threads**), #31 (32 rev) | **Now rmems.** #39 (streaming shared_vectors tests) is the densest wave B candidate found in the scan |
| [limbic-critic](https://github.com/rmems/limbic-critic) | #29 (10 rev), #30 (7 rev) | **Now rmems.** Dep decoupling + surprise semantics; later PRs are docs/REUSE/publish-prep — excluded |
| [plasticity-lab](https://github.com/Limen-Neural/plasticity-lab) | — | Recent history is Dependabot-dominated (8 of last 8 merged are chores/dep bumps); low priority until a code wave lands |
| [brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon) | #8 (**215 rev / 57 threads**), #24 (56 rev), #25 (18 rev) | #8 (resolve issues #4–#7) is the largest raw review count seen org-wide; #24 corpus-ipc decoupling |
| [synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh) | #8 (51 rev), #13 (71 rev), #25 (21 rev) | Neuromodulatory router feature + license/CI repair with real review traffic |
| [nir-rs](https://github.com/Limen-Neural/nir-rs) | #38 (61 rev / 37 threads), #33 (5 rev), #36 (2 rev) | Repo now past #40. #38 Docker dual-publish is the standout; #33–#36 release-gate ladder is thinner than expected |

Full wave B shortlists land when issue #28 is decomposed.

Cross-repo exclusion policy lives in [_index.md](_index.md#avoid-for-v0-training).
