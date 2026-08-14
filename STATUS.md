# STATUS — Operation Prometheus

**Last updated:** 2026-08-12  
**By:** Grok Build Agent: Grok 4.5 (xAI)

## Accomplished this sprint

1. **Read-only GitHub collector** (`scripts/collect_pr_records.py` + `scripts/lib/`) — merged PR #12  
2. **Normalizer** → schema-valid JSONL with quality scores, bot filter, secret redaction  
3. **corinth-canal-v0** — 6 trajectories extracted and merged  
4. **Limen-Neural Wave A pilot** — shortlist docs + **limen-axon-encoder-v0** (3 PRs)  
   - JSONL: `datasets/jsonl/limen-axon-encoder-v0.jsonl`  
   - Card/manifest under `datasets/cards/` and `datasets/manifests/`  
   - Source: `docs/source-repos.md` (Limen-Neural section)  
5. **grok-ozempic-v0** — **8** trajectories (was 7; **#42** Python export added via #20)  
6. **#18/#19** — review_signals dedupe + `language_by_pr` (merged #34)  
7. **#14** — `PROMETHEUS_DATA_ROOT` sibling layout (merged #22); package **0.4.0** tagged  
8. **Tracker** — GH #13/#15 + Linear RM-172/RM-173  

## Trajectory quality (grok-ozempic-v0 #42)

| PR | language | training_use | quality | Notes |
|----|----------|--------------|---------|--------|
| #42 | **Python** | review-to-patch | 0.90 | pickle→`.npy` export; 8 unique signals post-dedupe; advances #37 |

## Remaining gaps

- Schema v0 lacks `training_use: feature` (mapped to `other`)  
- Later Limen waves (neuromod, SpikeStream, kinetic-signals, limbic-critic) not extracted  
- Large patches still truncated; bot review noise high on Limen PRs  
- Manual human re-inspection sample still recommended before training runs  

## Next-sprint roadmap (prioritized)

1. **Close v0.5 epic #31** once #20 lands  
2. **v0.6 fleet extracts** — myelin-accelerator (#21), shortlist refreshes, Limen Wave B+  
3. **Schema v0.1** — add `feature` to `training_use`  
4. **SFT / preference pairs** — v0.7 (#23)  

## Verification checklist

```bash
ruff check scripts/
pytest -q
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
```
