# Dataset Card: brainstem-daemon trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [brainstem-daemon-v0.jsonl](../jsonl/brainstem-daemon-v0.jsonl)  
**Machine card:** [brainstem-daemon-v0.json](brainstem-daemon-v0.json)  
**Manifest:** [brainstem-daemon-v0.manifest.json](../manifests/brainstem-daemon-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/brainstem-daemon.md](../../docs/source-repos/brainstem-daemon.md)

## Source repository

- **Repo:** [Limen-Neural/brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon)
- **Description:** SNN runtime daemon (ServiceRegistry, optional corpus-ipc/ZMQ, neuron-count validation)
- **Language:** Rust

## Included PRs (4)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#8](https://github.com/Limen-Neural/brainstem-daemon/pull/8) | feature | feature | infra | 0.95 |
| [#24](https://github.com/Limen-Neural/brainstem-daemon/pull/24) | review-to-patch | review-to-patch | api | 0.95 |
| [#25](https://github.com/Limen-Neural/brainstem-daemon/pull/25) | repair | repair | snn | 0.95 |
| [#3](https://github.com/Limen-Neural/brainstem-daemon/pull/3) | feature | feature | snn | 0.85 |

## Narrative buckets

1. **Library runtime** — ServiceRegistry + `BrainstemDaemon` (#8).
2. **Optional IPC** — local ingress/egress traits, stub backend (#24); neuromod 0.4 + corpus-ipc migrate (#3).
3. **Construction safety** — fallible neuron-count validation (#25).

## Intended training uses

- Feature: daemon library split and ZMQ wiring.
- Review-to-patch: corpus-ipc decoupling under heavy review.
- Repair: panic → `Result` for neuron-count overflow.

## Known limitations (v0)

- `#8` also lands CI and dual-license files; the domain signal is the registry/runtime split.
- Four-PR Wave B+ pilot (remaining merged PRs are docs, qodana, or `target/` dumps).
- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
unset GH_TOKEN
python3 scripts/collect_pr_records.py \
  --repo Limen-Neural/brainstem-daemon --pr 8,24,25,3

python3 scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/Limen-Neural_brainstem-daemon \
  --card datasets/cards/brainstem-daemon-v0.json \
  --out datasets/jsonl/brainstem-daemon-v0.jsonl \
  --pr 8,24,25,3 --strict

python3 scripts/validate_jsonl.py --strict-policy datasets/jsonl/brainstem-daemon-v0.jsonl

python3 scripts/build_manifest.py --jsonl datasets/jsonl/brainstem-daemon-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-20 for Limen Wave B+ (operation-prometheus #28).
