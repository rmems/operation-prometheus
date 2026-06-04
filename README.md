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

## Long-Term Vision

Operation Prometheus aims to become a personal engineering memory system capable of teaching future local models how software evolves through review, experimentation, validation, and iteration.

The goal is not merely code generation.

The goal is engineering understanding.
