# synaptic-mesh

<!-- index: [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh) | v0 extracted -->

**Repo**: [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh)  
**Description**: SNN topology — CSR sparse maps, ChannelRouter, neuromodulatory adaptation  
**Language**: Rust  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/synaptic-mesh-v0.jsonl](../../datasets/jsonl/synaptic-mesh-v0.jsonl)  
**Metadata card**: [datasets/cards/synaptic-mesh-v0.json](../../datasets/cards/synaptic-mesh-v0.json)

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#8](https://github.com/Limen-Neural/synaptic-mesh/pull/8) | feat(router): neuromodulatory adaptation | snn | feature | 53 kept / 8 emitted. Dopamine/cortisol/serotonin + plasticity. |
| [#7](https://github.com/Limen-Neural/synaptic-mesh/pull/7) | refactor(router): AhlRouter → ChannelRouter | api | repair | 28 kept. Implements #6. documentation label overridden to refactor. |
| [#30](https://github.com/Limen-Neural/synaptic-mesh/pull/30) | refactor: inline NeuromodNeuron in router | snn | repair | 4 kept. Delete standalone neuromod module. |
| [#2](https://github.com/Limen-Neural/synaptic-mesh/pull/2) | Feat/overhaul | snn | feature | 4 kept. GIF neuron + AhlRouter. |
| [#1](https://github.com/Limen-Neural/synaptic-mesh/pull/1) | feat: CSR sparse synaptic map | snn | feature | 1 kept. Domain origin; sparse map + SAAQ telemetry. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #8 | 53 | 8 | 8 | shortlisted |
| #7 | 28 | 8 | 8 | shortlisted |
| #30 | 4 | 4 | 4 | shortlisted |
| #2 | 4 | 4 | 4 | shortlisted |
| #1 | 1 | 1 | 1 | shortlisted (origin PR) |

## Considered and rejected

- Qodana, REVIEW.md, docs-link, license/CI PRs — skip list.
