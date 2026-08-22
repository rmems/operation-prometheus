# Dataset Card: worktrees-hives trajectories v0

**Status:** experimental, manually curated  
**Created by:** Grok Build Agent: Grok 4.5  
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)  
**JSONL:** [worktrees-hives-v0.jsonl](../jsonl/worktrees-hives-v0.jsonl)  
**Machine card:** [worktrees-hives-v0.json](worktrees-hives-v0.json)  
**Manifest:** [worktrees-hives-v0.manifest.json](../manifests/worktrees-hives-v0.manifest.json)  
**Shortlist source:** [docs/source-repos/worktrees-hives.md](../../docs/source-repos/worktrees-hives.md)

## Source repository

- **Repo:** [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives)
- **Description:** Multi-agent hypothesis lab — agents/subagents in isolated git worktrees, mandatory JSON + Markdown findings, Python/Rust hybrid safety cage, never auto-merges
- **Language:** Python (Rust `wh-core` on `#65` via `language_by_pr`)

## Included PRs (5)

| PR | Bucket (card) | Schema `training_use` | Domain | Quality |
|----|---------------|----------------------|--------|---------|
| [#61](https://github.com/rmems/worktrees-hives/pull/61) | feature | feature | agentic-workflow | 0.90 |
| [#63](https://github.com/rmems/worktrees-hives/pull/63) | feature | feature | agentic-workflow | 0.95 |
| [#65](https://github.com/rmems/worktrees-hives/pull/65) | feature | feature | ml-infra | 0.90 |
| [#78](https://github.com/rmems/worktrees-hives/pull/78) | review-to-patch | review-to-patch | tools | 0.95 |
| [#79](https://github.com/rmems/worktrees-hives/pull/79) | review-to-patch | review-to-patch | tools | 0.90 |

## Narrative buckets

1. **Claim / isolation** — issue → branch → worktree claim with no local `git` fallback (#61).
2. **Never auto-merge** — issue→PR orchestrator with a hard safety invariant (#63).
3. **Hybrid foundation** — Rust `wh-core` sandbox + Python `WhClient` bridge (#65).
4. **CLI surface + review patch** — discover/plan/babysit wired into the CLI (#78) then CodeAnt/CodeRabbit follow-up (#79).

## Intended training uses

- Local SFT / process-supervision for coding agents working on multi-agent git worktree labs.
- Feature trajectories: claim isolation, never-auto-merge PR workflow, hybrid Python/Rust foundation.
- Review-to-patch: #78/#79 pair (must emit ≥1 review signal; #79 is the low-yield patch half).

## Known limitations (v0)

- Large PR patches may be truncated to ~96 KiB; full diffs live only under gitignored `datasets/raw/`.
- Review noise is high; CodeAnt/Macroscope/Codecov are filtered; engineering review bots (Gemini/Codex) are retained.
- `#79` emits only 2 unique review signals; it is in the set as the patch of `#78`, not as a yield leader.
- `#65` `Closes #24 #25 …` only yields `#24` from the close-keyword parser; remaining issues are card `linked_issues_by_pr`.
- Lab-CLI wave `#90`/`#88`/`#103`/`#105` is deferred, not rejected.
- Solo-maintainer merges: multi-human review is limited.
- **Not for:** training on secrets, private configs, model weights, or closed-model chat logs.

## Collection pipeline

```bash
export GITHUB_TOKEN=...
unset GH_TOKEN
python3 scripts/collect_pr_records.py \
  --repo rmems/worktrees-hives --pr 61,63,65,78,79

python3 scripts/build_trajectory_jsonl.py \
  --raw-dir datasets/raw/rmems_worktrees-hives \
  --card datasets/cards/worktrees-hives-v0.json \
  --out datasets/jsonl/worktrees-hives-v0.jsonl \
  --pr 61,63,65,78,79

python3 scripts/validate_jsonl.py --strict-policy datasets/jsonl/worktrees-hives-v0.jsonl

python3 scripts/build_manifest.py --jsonl datasets/jsonl/worktrees-hives-v0.jsonl \
  --created-at 2026-08-20 --created-by "Grok Build Agent: Grok 4.5"
```

## License / provenance

Source PRs are public GitHub engineering history under the source repository license. This dataset is a derived, curated projection for research and local model training. v0 is experimental. Extracted 2026-08-20 for the v0.6 Fleet milestone.
