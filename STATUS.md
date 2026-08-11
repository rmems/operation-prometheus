# STATUS — Operation Prometheus

**Last updated:** 2026-08-11  
**By:** Grok Build Agent: Grok 4.5 (xAI)

## Accomplished this sprint

1. **Read-only GitHub collector** (`scripts/collect_pr_records.py` + `scripts/lib/`) — merged PR #12  
2. **Normalizer** → schema-valid JSONL with quality scores, bot filter, secret redaction  
3. **corinth-canal-v0** — 6 trajectories extracted and merged  
4. **Limen-Neural Wave A pilot** — shortlist docs + **limen-axon-encoder-v0** (3 PRs)  
   - JSONL: `datasets/jsonl/limen-axon-encoder-v0.jsonl`  
   - Card/manifest under `datasets/cards/` and `datasets/manifests/`  
   - Source: `docs/source-repos.md` (Limen-Neural section)  
5. **grok-ozempic-v0** — 7 trajectories extracted (#11)  
6. **Tracker** — GH #13/#15 + Linear RM-172/RM-173  

## Trajectory quality (limen-axon-encoder-v0)

| PR | training_use | quality | Notes |
|----|--------------|---------|--------|
| #37 | review-to-patch | 0.95 | Gain curves; closes #26; strong review density |
| #50 | repair | 0.95 | RNG security swap |
| #41 | review-to-patch | 0.95 | Encoder standardize; bot-heavy |

## Remaining gaps

- Schema v0 lacks `training_use: feature` (mapped to `other`)  
- **#14** sibling data root — implemented on `feat/issue-14-prometheus-data-root` (`PROMETHEUS_DATA_ROOT`, `--skip-existing`, `list_merged_prs.py`); package version **0.4.0**  
- Later Limen waves (neuromod, SpikeStream, kinetic-signals, limbic-critic) not extracted  
- Large patches still truncated; bot review noise high on Limen PRs  
- Manual human re-inspection sample still recommended before training runs  

## Next-sprint roadmap (prioritized)

1. **Review-signal dedupe** (#18) + **`language_by_pr`** (#19) — both block grok-ozempic#42 (#20)  
2. **Sibling data root** (#14) — PR in progress (`feat/issue-14-prometheus-data-root`)  
3. **Limen Wave B** — neuromod #5/#8/#9 or SpikeStream #22/#25  
4. **Schema v0.1** — add `feature` to `training_use`  
5. **SFT export adapter** — JSONL → chat/process-supervision pairs  

## Verification checklist

```bash
ruff check scripts/
pytest -q
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
```
