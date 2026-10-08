---
license:
- apache-2.0
- mit
pretty_name: Operation Prometheus trajectories
tags:
- code
- software-engineering
- pull-requests
- code-review
- trajectories
size_categories:
- n<1K
---

# Operation Prometheus — software-engineering trajectories

Pull-request engineering trajectories extracted from public GitHub history by
[operation-prometheus](https://github.com/rmems/operation-prometheus):
issue/review signal → code state → patch → validation → outcome.

- **Records:** 97
- **Format:** JSONL (`trajectories.jsonl`), schema `pr_trajectory_v0` / `trajectory_v1`
- **Languages:** Julia, Python, Rust, SystemVerilog
- **Generated:** 2026-10-08 · sha256 `d0bc760dc74ad8cf…`

## Record fields

`id`, `repo`, `pr_number`, `source_urls`, `language`, `domain`, `task_type`,
`before_context`, `patch`, `validation`, `outcome`, `training_use`,
`issue_context`, `review_signals`, `quality_score`, `source_license`.

`training_use` buckets:

| Bucket | Records |
|--------|---------|
| `bug-prediction` | 3 |
| `feature` | 39 |
| `repair` | 22 |
| `review-to-patch` | 22 |
| `validation` | 11 |

## Source repositories and license / provenance

Each record's `source_license` is the license of its originating repository —
this dataset is **not** under a single blanket license. The export tooling and
schemas are Apache-2.0; that does not relicense source-derived content.
License set represented: Apache-2.0; MIT; MIT OR Apache-2.0.

| Repository | Records | Source license |
|------------|---------|----------------|
| [Limen-Neural/axon-encoder](https://github.com/Limen-Neural/axon-encoder) | 3 | MIT OR Apache-2.0 |
| [Limen-Neural/brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon) | 4 | MIT OR Apache-2.0 |
| [Limen-Neural/neuromod](https://github.com/Limen-Neural/neuromod) | 5 | MIT OR Apache-2.0 |
| [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs) | 4 | MIT OR Apache-2.0 |
| [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh) | 5 | MIT OR Apache-2.0 |
| [rmems/LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl) | 3 | MIT OR Apache-2.0 |
| [rmems/SpikeStream.jl](https://github.com/rmems/SpikeStream.jl) | 4 | MIT OR Apache-2.0 |
| [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry) | 5 | MIT |
| [rmems/agoge-forger](https://github.com/rmems/agoge-forger) | 4 | Apache-2.0 |
| [rmems/corinth-canal](https://github.com/rmems/corinth-canal) | 12 | MIT OR Apache-2.0 |
| [rmems/engram-parser](https://github.com/rmems/engram-parser) | 1 | MIT OR Apache-2.0 |
| [rmems/grok-ozempic](https://github.com/rmems/grok-ozempic) | 13 | MIT OR Apache-2.0 |
| [rmems/kinetic-signals](https://github.com/rmems/kinetic-signals) | 5 | MIT OR Apache-2.0 |
| [rmems/limbic-critic](https://github.com/rmems/limbic-critic) | 4 | MIT OR Apache-2.0 |
| [rmems/myelin-accelerator](https://github.com/rmems/myelin-accelerator) | 5 | MIT OR Apache-2.0 |
| [rmems/silicon-hdl](https://github.com/rmems/silicon-hdl) | 5 | MIT OR Apache-2.0 |
| [rmems/spike-viz](https://github.com/rmems/spike-viz) | 3 | Apache-2.0 |
| [rmems/thalamic-relay](https://github.com/rmems/thalamic-relay) | 3 | MIT OR Apache-2.0 |
| [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives) | 5 | Apache-2.0 |
| [rmems/xai-dissect](https://github.com/rmems/xai-dissect) | 4 | MIT OR Apache-2.0 |

## Intended use

SFT / process-supervision for coding agents: feature implementation, repair,
validation discipline, and especially **review-to-patch** — responding to human
review comments with corrective commits.

## Exclusions and limitations

Per the [data policy](https://github.com/rmems/operation-prometheus/blob/main/docs/data-policy.md):
no secrets, private configs, model weights, closed-model chat logs, or bot
boilerplate (review bots like Gemini/Codex are retained as signal). Large
patches may be truncated (~96 KiB cap). Solo-maintainer repos: limited
multi-human review. Inspect records before training use.
