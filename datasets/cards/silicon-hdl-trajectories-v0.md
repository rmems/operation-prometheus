# Dataset Card: silicon-hdl trajectories v0

**Status:** experimental, manually curated  
**Created by:** Cursor agent  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [silicon-hdl-v0.jsonl](../jsonl/silicon-hdl-v0.jsonl)  
**Machine card:** [silicon-hdl-v0.json](silicon-hdl-v0.json)  
**Manifest:** [silicon-hdl-v0.manifest.json](../manifests/silicon-hdl-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/silicon-hdl.md](../../docs/source-repos/silicon-hdl.md)

## Source repository

- **Repo:** [rmems/silicon-hdl](https://github.com/rmems/silicon-hdl)
- **Description:** SystemVerilog SNN core/SoC
- **Language:** SystemVerilog

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#81](https://github.com/rmems/silicon-hdl/pull/81) | feature | feature | hdl | 0.95 |
| [#51](https://github.com/rmems/silicon-hdl/pull/51) | feature | feature | hdl | 0.95 |
| [#52](https://github.com/rmems/silicon-hdl/pull/52) | feature | feature | hdl | 0.95 |
| [#15](https://github.com/rmems/silicon-hdl/pull/15) | review-to-patch | review-to-patch | hdl | 0.95 |
| [#11](https://github.com/rmems/silicon-hdl/pull/11) | repair | repair | hdl | 0.90 |

## Narrative buckets

1. **INIT_FILE ladder** — E1 `$readmemh` RAMs (#51) then E2 Basys3 generics (#52).
2. **Time-multiplexed LIF PE** (#81).
3. **Review-to-RTL** — leftover bot comments (#15) and LifNeuron spike-reset (#11).

## Known limitations (v0)

- `language_for` does not sniff `.sv`; card `language` is SystemVerilog.
- **Not for:** secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py --repo rmems/silicon-hdl --pr 81,51,52,15,11 --skip-existing
python scripts/build_trajectory_jsonl.py --raw-dir datasets/raw/rmems_silicon-hdl --card datasets/cards/silicon-hdl-v0.json --out datasets/jsonl/silicon-hdl-v0.jsonl --pr 81,51,52,15,11
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/silicon-hdl-v0.jsonl
python scripts/build_manifest.py --jsonl datasets/jsonl/silicon-hdl-v0.jsonl --created-at 2026-09-04 --created-by "Cursor agent"
```
