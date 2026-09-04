# Dataset Card: synaptic-mesh trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [synaptic-mesh-v0.jsonl](../jsonl/synaptic-mesh-v0.jsonl)  
**Machine card:** [synaptic-mesh-v0.json](synaptic-mesh-v0.json)  
**Manifest:** [synaptic-mesh-v0.manifest.json](../manifests/synaptic-mesh-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/synaptic-mesh.md](../../docs/source-repos/synaptic-mesh.md)

## Source repository

- **Repo:** [Limen-Neural/synaptic-mesh](https://github.com/Limen-Neural/synaptic-mesh)
- **Description:** SNN topology library (CSR, ChannelRouter, neuromodulatory adaptation)
- **Language:** Rust

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#8](https://github.com/Limen-Neural/synaptic-mesh/pull/8) | feature | feature | snn | 0.95 |
| [#7](https://github.com/Limen-Neural/synaptic-mesh/pull/7) | repair | repair | api | 0.90 |
| [#30](https://github.com/Limen-Neural/synaptic-mesh/pull/30) | repair | repair | snn | 0.90 |
| [#2](https://github.com/Limen-Neural/synaptic-mesh/pull/2) | feature | feature | snn | 0.75 |
| [#1](https://github.com/Limen-Neural/synaptic-mesh/pull/1) | feature | feature | snn | 0.90 |

## Narrative buckets

1. **Router generalization** — AhlRouter → ChannelRouter (#7) then neuromodulatory channels (#8).
2. **Module inlining** — NeuromodNeuron into router (#30).
3. **GIF + CSR origin** (#2, #1).

## Known limitations (v0)

- #1 has a single kept review signal; kept as the CSR origin PR.
- #7 GitHub label includes documentation; card forces refactor.
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo Limen-Neural/synaptic-mesh --pr 8,7,30,2,1 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/Limen-Neural_synaptic-mesh --card datasets/cards/synaptic-mesh-v0.json --out datasets/jsonl/synaptic-mesh-v0.jsonl --pr 8,7,30,2,1
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/synaptic-mesh-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/synaptic-mesh-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
