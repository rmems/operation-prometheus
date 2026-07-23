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

## Extraction Shortlists

- **corinth-canal v0** (extracted): [docs/source-repos.md](docs/source-repos.md). 6 high-signal merged PRs → [datasets/jsonl/corinth-canal-v0.jsonl](datasets/jsonl/corinth-canal-v0.jsonl). Cards: [JSON](datasets/cards/corinth-canal-v0.json), [markdown](datasets/cards/corinth-canal-trajectories-v0.md). Manifest: [corinth-canal-v0.manifest.json](datasets/manifests/corinth-canal-v0.manifest.json).
- **grok-ozempic v0** (shortlist only): documented in [docs/source-repos.md](docs/source-repos.md); card [datasets/cards/grok-ozempic-v0.json](datasets/cards/grok-ozempic-v0.json).
- **Format**: JSONL (one trajectory record per line, conforming to schema v0). See [datasets/README.md](datasets/README.md).
- **Sprint status**: [STATUS.md](STATUS.md)

## Collect and normalize (read-only)

Requires public GitHub access. A token is optional but strongly recommended for rate limits.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GITHUB_TOKEN=...   # optional; higher rate limits

# Issue #5 — collect raw PR records (gitignored under datasets/raw/)
python scripts/collect_pr_records.py \
  --repo rmems/corinth-canal \
  --pr 82,89,91,94,95,96 \
  --out-dir datasets/raw/corinth-canal

# Issue #6 — normalize to schema-compliant JSONL
python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/corinth-canal \
  --card datasets/cards/corinth-canal-v0.json \
  --out datasets/jsonl/corinth-canal-v0.jsonl

# Validate (schema + optional policy hygiene)
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/corinth-canal-v0.jsonl
```

The collector performs **no write operations** to GitHub. Raw dumps must stay out of git (`datasets/raw/` is ignored).

