# Dataset Card: thalamic-relay trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [thalamic-relay-v0.jsonl](../jsonl/thalamic-relay-v0.jsonl)  
**Machine card:** [thalamic-relay-v0.json](thalamic-relay-v0.json)  
**Manifest:** [thalamic-relay-v0.manifest.json](../manifests/thalamic-relay-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/thalamic-relay.md](../../docs/source-repos/thalamic-relay.md)

## Source repository

- **Repo:** [rmems/thalamic-relay](https://github.com/rmems/thalamic-relay)
- **Description:** GPU-safety supervisor / thalamic relay (thermal and power brakes, IPC)
- **Language:** Rust

## Included PRs (3)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#20](https://github.com/rmems/thalamic-relay/pull/20) | feature | feature | gpu-compute | 0.95 |
| [#23](https://github.com/rmems/thalamic-relay/pull/23) | repair | repair | gpu-compute | 0.95 |
| [#22](https://github.com/rmems/thalamic-relay/pull/22) | validation | validation | systems | 0.90 |

## Narrative buckets

1. **GPU safety in the loop** — threshold-based `SafetyStatus` and emergency brake (#20).
2. **Brake recovery** — stale telemetry after `release_task` (#23).
3. **Supervisor/IPC tests** — fail-closed UDP JSON handling (#22).

## Collection pipeline

```bash
export GITHUB_TOKEN="$(gh auth token)"; unset GH_TOKEN
python scripts/collect_pr_records.py \
  --repo rmems/thalamic-relay --pr 20,23,22 \
  --out-dir datasets/raw/rmems_thalamic-relay

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_thalamic-relay \
  --card datasets/cards/thalamic-relay-v0.json \
  --out datasets/jsonl/thalamic-relay-v0.jsonl \
  --pr 20,23,22

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/thalamic-relay-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/thalamic-relay-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history. Extracted 2026-08-20 for Wave C (issue #29).
