# STATUS — Operation Prometheus

**Last updated:** 2026-07-21  
**By:** Grok Build Agent: Grok 4.5 (xAI)

## Accomplished this sprint

1. **Read-only GitHub collector** (`scripts/collect_pr_records.py` + `scripts/lib/`)
   - Rate-limit aware, token-optional REST client (stdlib urllib)
   - Collects PR body, comments, reviews, commits, files, unified diff, check-runs, linked issues
   - Secret / home-path redaction before write
   - Output: `datasets/raw/<repo-slug>/pr-N.json` (gitignored)

2. **Normalizer** (`scripts/build_trajectory_jsonl.py`)
   - Card overlay for language/domain/buckets
   - Bot filtering with engineering-review allowlist (Gemini/Codex)
   - Schema mapping: feature bucket → `training_use: other`
   - Patch size budget + truncation footer

3. **Extracted 6 corinth-canal trajectories**
   - `datasets/jsonl/corinth-canal-v0.jsonl` (schema + strict-policy validated)
   - Manifest: `datasets/manifests/corinth-canal-v0.manifest.json`
   - Quality scores: #94 0.94, #89 0.92, #82 0.86, #96 0.78, #91 0.62, #95 0.58

4. **Validation hardening**
   - `scripts/validate_jsonl.py --strict-policy` (canonical PR URL, no `/home/` paths, no secret hints)
   - Unit tests: 8 passed (fixtures, no network)

5. **Documentation**
   - Markdown dataset card (issue #7 AC)
   - Updated JSON card to `extracted-v0`
   - Expanded shortlist: **grok-ozempic** (6 PRs) + myelin-accelerator watchlist
   - README collector commands

6. **Tracker work**
   - GitHub issues #5, #6, #7 advanced/closed with evidence
   - Linear RM-112 / RM-113 / RM-114 mirrored where possible

## Quality notes on trajectories

| PR | Strength | Weakness |
|----|----------|----------|
| #94 | Best review→fix quant path (packed Int4 size) | Large test delta |
| #89 | Full validation ladder + sanitizer evidence | — |
| #82 | Core Q6_K dequant + shared loader | Test relocation bloat; patch curated via size cap |
| #96 | Clean tooling; full patch fits | Partial close of #90 |
| #91 | Multi-issue feature richness | 35 files; thinner coverage signal |
| #95 | RunMatrix validate + multi-model ops | Lowest quality; local path redaction required |

## Remaining gaps

- Schema v0 lacks `training_use: feature` (mapped to `other`)
- grok-ozempic shortlist not yet extracted to JSONL
- myelin-accelerator shortlist not carded as first-class v0 extract
- Large patches still truncated; no multi-record split for #91/#95
- No live CI artifact deep links in `validation` beyond check-run names
- Manual human re-inspection sample still recommended before training runs

## Next-sprint roadmap (prioritized)

1. **Extract grok-ozempic-v0** (PRs 29, 26, 24, 25, 11, 8) with same collector pipeline  
2. **Schema v0.1** — add `feature` (and maybe `tools`) to `training_use` enum; re-emit cards  
3. **Split-record option** for multi-issue PRs (#91, #95, grok #29) into coherent sub-trajectories  
4. **Review-signal ranking** — prefer Gemini/Codex comments that mention bugs/security over nits  
5. **myelin-accelerator card** after #22 merges; extract #18 and #2/#6/#7 chain  
6. **SFT export adapter** — convert JSONL to chat/process-supervision pairs for local Unsloth/QLoRA  
7. **CI live-collect optional job** (token secret) producing raw outside repo + validating committed JSONL only  

## Verification checklist

```bash
ruff check scripts/
pytest -q
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
```

All three should pass on main after this sprint lands.
