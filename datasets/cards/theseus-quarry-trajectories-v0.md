# Dataset Card: Theseus-Quarry trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [theseus-quarry-v0.jsonl](../jsonl/theseus-quarry-v0.jsonl)  
**Machine card:** [theseus-quarry-v0.json](theseus-quarry-v0.json)  
**Manifest:** [theseus-quarry-v0.manifest.json](../manifests/theseus-quarry-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/theseus-quarry.md](../../docs/source-repos/theseus-quarry.md)

## Source repository

- **Repo:** [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry)
- **Description:** Crypto-mining telemetry extraction for neuromorphic-computing research (miner HTTP APIs, JSONL telemetry, GPU signaling)
- **Language:** Rust

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#13](https://github.com/rmems/Theseus-Quarry/pull/13) | feature | feature | telemetry | 0.95 |
| [#9](https://github.com/rmems/Theseus-Quarry/pull/9) | feature | feature | gpu-compute | 0.90 |
| [#12](https://github.com/rmems/Theseus-Quarry/pull/12) | repair | repair | telemetry | 0.90 |
| [#11](https://github.com/rmems/Theseus-Quarry/pull/11) | feature | feature | telemetry | 0.90 |
| [#8](https://github.com/rmems/Theseus-Quarry/pull/8) | repair | repair | infra | 0.95 |

## Narrative buckets

1. **HTTP MinerPerf migration** — stdout scrape → BzMiner/XMRig/OneZeroMiner HTTP APIs (#13).
2. **GPU thermal safety** — process SIGSTOP/SIGCONT from telemetry-collector (#9); scheduler migration out of the deleted supervisor (#8).
3. **Endpoint correctness** — configurable miner API ports and node RPC URLs (#12).
4. **JSONL operations** — daily file rotation and retention (#11).
5. **Supervisor amputation** — remove `theseus-mining` (−5442 lines) while keeping thermal governance (#8).

## Intended training uses

- Local SFT / process-supervision for coding agents working on telemetry collectors, miner HTTP APIs, and GPU thermal signaling.
- Feature trajectories: HTTP collection, thermal process signaling, JSONL rotation.
- Repair trajectories: endpoint alignment (#12) and architectural crate removal (#8).

## Known limitations (v0)

- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- Review noise is high; CodeAnt/Macroscope/Codecov are filtered; engineering review bots (Gemini/Codex) are retained.
- `#12` (and related records) retain public loopback defaults such as `127.0.0.1:18081` from the open-source patch. Those are documented local miner/node RPC examples, not private LAN hosts. No RFC1918 addresses or internal DNS names were present on inspection.
- `#16` (config/docs) and `#18` (second-miner HTTP parser) are deferred, not rejected.
- Solo-maintainer merges: multi-human review is limited.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
python scripts/collect_pr_records.py \
  --repo rmems/Theseus-Quarry --pr 13,9,12,11,8

python scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_Theseus-Quarry \
  --card datasets/cards/theseus-quarry-v0.json \
  --out datasets/jsonl/theseus-quarry-v0.jsonl \
  --pr 13,9,12,11,8

python scripts/validate_jsonl.py --strict-policy datasets/jsonl/theseus-quarry-v0.jsonl

python scripts/build_manifest.py --jsonl datasets/jsonl/theseus-quarry-v0.jsonl \
  --created-at 2026-08-19 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-19 for the v0.6 Fleet milestone.
