# Limen Wave B+ (pilot + deferred)

<!-- index: [Limen Wave B+](https://github.com/Limen-Neural) | Wave B+ pilot extracted -->

**Scope**: issue [#28](https://github.com/rmems/operation-prometheus/issues/28) — twin-fleet expansion beyond [axon-encoder](limen-neural.md) (Wave A).  
**Pilot extracted 2026-08-20** (four dataset cards, 3–5 PRs each). Per-repo docs and cards live beside this file; this page is the **deferred remainder** plus the live-scan rationale.

Do **not** edit [limen-neural.md](limen-neural.md) from a Wave B extract — Wave A / axon-encoder lives there.

## Extracted this wave (pointers)

| Repo | Card | PRs | Why this wave |
|------|------|-----|---------------|
| [Limen-Neural/neuromod](neuromod.md) | [neuromod-v0](../../datasets/cards/neuromod-v0.json) | #5, #8, #9, #2, #15 | Issue smoke PRs still merged with yield; plus mining purge and domain-agnostic API. |
| [rmems/kinetic-signals](kinetic-signals.md) | [kinetic-signals-v0](../../datasets/cards/kinetic-signals-v0.json) | #39, #35, #17, #6, #1 | #39 densest Wave B candidate (109 raw reviews). |
| [rmems/SpikeStream.jl](spikestream-jl.md) | [spikestream-jl-v0](../../datasets/cards/spikestream-jl-v0.json) | #7, #25, #22, #21 | Boundary cut + fixtures; skipped higher-raw #18/#20 (CI/docs). |
| [Limen-Neural/brainstem-daemon](brainstem-daemon.md) | [brainstem-daemon-v0](../../datasets/cards/brainstem-daemon-v0.json) | #8, #24, #25, #3 | #8 largest raw-review PR org-wide; #24 corpus-ipc decoupling. |

## Deferred (live list_merged_prs.py, 2026-08-20)

| Repo | Candidate PRs (issue / docs) | Why deferred |
|------|------------------------------|--------------|
| [rmems/limbic-critic](https://github.com/rmems/limbic-critic) | #30, #29; older #2/#1 | #30 (Replace SimpleCritic acetylcholine placeholder) is domain; later merged history is REUSE/CHANGELOG/publish-prep/docs. Keep a dedicated extract for #30/#29 after Wave B+ pilot. |
| [Limen-Neural/plasticity-lab](https://github.com/Limen-Neural/plasticity-lab) | #26, #25 | #26/#25 have titles with domain signal (limbic-critic bridge / API drift) but the surrounding merge history is Dependabot-dominated. Revisit as a 3-PR card once bot noise is filtered in a dedicated pass. |
| [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh) | #1, #8, #30; docs also #13 | Real router/CSR feature PRs (#8 neuromodulatory adaptation, #1 CSR map, #30 inline NeuromodNeuron). Deferred to keep this PR at four cards. |
| [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs) | #24, #23, #20, #18; docs #38 | Domain IO/graph PRs exist (`feat(graph)` serde, untrusted-read harden, HDF5 `.nir`, Core IR). #38 is Docker dual-publish — skip if that is all it is. Deferred so Wave B+ stays a small pilot. |

## Live-scan notes (not extracted)

- **neuromod #96–#98**: 42/23/15 raw reviews — release/Docker-CI chain; prefer domain #5/#8/#9/#2/#15.
- **SpikeStream.jl #18/#20**: 27/21 raw reviews — CI Codecov and AGENTS.md; no Julia domain delta.
- **kinetic-signals #37/#2**: 0 kept `extract_review_signals` after bot filter.
- **brainstem-daemon #1**: `target/` artifact dump; **#27**: empty collected patch.

Cross-repo exclusion policy: [_index.md](_index.md#avoid-for-v0-training).
