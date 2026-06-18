# Operation Prometheus

Operation Prometheus is a software-engineering trajectory forge.

The project extracts high-signal engineering artifacts from public repositories and transforms them into structured training datasets for local coding assistants, research agents, and future neuromorphic experiments.

Instead of treating source code as the primary training signal, Operation Prometheus focuses on engineering trajectories:

```text
Issue
↓
Implementation
↓
Review
↓
Fix
↓
Validation
↓
Merge
```

These trajectories capture the reasoning, debugging, validation, and repair process behind software engineering.

## Initial Goals

* Extract trajectory datasets from GitHub repositories
* Build Rust repair and autocomplete datasets
* Build Julia engineering datasets
* Create review-comment → patch training pairs
* Create bug-prediction and validation datasets
* Support future SAAQ(Spiking Adaptive Activity Quantization) and Spikenaut research

## Data Sources

Initial repositories include:

* corinth-canal
* xai-dissect
* grok-ozempic
* myelin-accelerator
* Surrogate_Viz.jl
* XAIDissect_Viz.jl
* agoge-forger
* Dioscuri-Cloud
* magere-brug
* Future Limen-Neural projects

## Repository Layout

- [docs/](docs/) — documentation and guides (including [data-policy.md](docs/data-policy.md))
- [schemas/](schemas/) — data and trajectory schemas (JSON Schema v0 draft)
- [providers/](providers/) — thin clients, adapters and config for external model / inference providers (no weights or large artifacts)
- [scripts/](scripts/) — extraction, transformation, and validation scripts
- [datasets/](datasets/) — local dataset outputs (raw data under `datasets/raw/` is gitignored; only small curated examples, cards, and manifests may be committed — see [datasets/README.md](datasets/README.md))
- [evals/](evals/) — evaluation assets and prompts

See [datasets/README.md](datasets/README.md) for rules on what may be committed.

## Schemas and Data Policy

- **Schema v0** (initial draft, not final): [schemas/pr_trajectory.schema.json](schemas/pr_trajectory.schema.json). Implements GitHub [#2](https://github.com/rmems/operation-prometheus/issues/2). See the tiny example in `datasets/examples/`.
- **Data policy & hygiene**: [docs/data-policy.md](docs/data-policy.md). Implements GitHub [#3](https://github.com/rmems/operation-prometheus/issues/3). Covers allowed public sources, excluded material, manual inspection requirement, and the distinction between public engineering history vs. raw chat log scraping.

These are tracked in the global beads DB (prefix `raulmc-`): `raulmc-vge` and `raulmc-9cq`.


