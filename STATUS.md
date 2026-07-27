# STATUS — Operation Prometheus

**Last updated:** 2026-07-24  
**By:** Grok Build Agent: Grok 4.5 (xAI)

## Accomplished this sprint

1. **Read-only GitHub collector** (`scripts/collect_pr_records.py` + `scripts/lib/`) — merged PR #12  
2. **Normalizer** → schema-valid JSONL with quality scores, bot filter, secret redaction  
3. **corinth-canal-v0** — 6 trajectories extracted and merged  
4. **Limen-Neural Wave A pilot** — shortlist docs + **limen-axon-encoder-v0** (3 PRs)  
   - JSONL: `datasets/jsonl/limen-axon-encoder-v0.jsonl`  
   - Card/manifest under `datasets/cards/` and `datasets/manifests/`  
   - Source: `docs/source-repos.md` (Limen-Neural section)  
5. **Tracker** — GH #13/#15 + Linear RM-172/RM-173; #11 grok-ozempic still open  

## Trajectory quality (limen-axon-encoder-v0)

| PR | training_use | quality | Notes |
|----|--------------|---------|--------|
| #37 | review-to-patch | 0.95 | Gain curves; closes #26; strong review density |
| #50 | repair | 0.95 | RNG security swap |
| #41 | review-to-patch | 0.95 | Encoder standardize; bot-heavy |

## Remaining gaps

- Schema v0 lacks `training_use: feature` (mapped to `other`)  
- **#11** grok-ozempic-v0 shortlist not yet extracted  
- **#14** sibling data root for large patches not yet documented as env default  
- Later Limen waves (neuromod, SpikeStream, kinetic-signals, limbic-critic) not extracted  
- Large patches still truncated; bot review noise high on Limen PRs  
- Manual human re-inspection sample still recommended before training runs  

## Next-sprint roadmap (prioritized)

1. **Extract grok-ozempic-v0** (#11) — PRs 29, 26, 24, 25, 11, 8  
2. **Sibling data root** (#14) — `PROMETHEUS_DATA_ROOT` for raw/full patches  
3. **Limen Wave B** — neuromod #5/#8/#9 or SpikeStream #22/#25  
4. **Schema v0.1** — add `feature` to `training_use`  
5. **SFT export adapter** — JSONL → chat/process-supervision pairs  

## Verification checklist

```bash
ruff check scripts/
pytest -q
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
```
