# worktrees-hives

<!-- index: [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives) | shortlist drafted -->

**Repo**: [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives)  
**Description**: Multi-agent hypothesis lab — agents/subagents in isolated git worktrees, mandatory JSON + Markdown findings, Python/Rust hybrid safety cage, never auto-merges  
**Language**: Python (+ Rust `wh-core`)  
**Status**: shortlist **drafted** (2026-08-16 live scan, issue [#30](https://github.com/rmems/operation-prometheus/issues/30)) — not extracted; v0.6 agentic-workflow priority

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#61](https://github.com/rmems/worktrees-hives/pull/61) | Issue #6: Claim issue → branch → worktree isolation | agentic-workflow | feature | Densest PR in the repo: 80 reviews / 90 threads on +644 lines. Closes #6. |
| [#65](https://github.com/rmems/worktrees-hives/pull/65) | Foundation: R1–R3, R5, P1, H1, H3 (hybrid docs + Rust core + Python bridge) | agentic-workflow, ml-infra | feature | 60 reviews / 85 threads; +1736/−57 across 22 files; the hybrid-architecture cut. Closes #24. |
| [#63](https://github.com/rmems/worktrees-hives/pull/63) | Issue #8: Issue → PR workflow (never auto-merge) | agentic-workflow | feature | 53 reviews / 40 threads on +1221 lines; safety-invariant design under review. Closes #8. |
| [#78](https://github.com/rmems/worktrees-hives/pull/78) | Wire discover/plan/babysit into the CLI | agentic-workflow, tools | review-to-patch | 24 reviews / 19 threads, 12 commits; paired with follow-up #79. Closes #76. |
| [#79](https://github.com/rmems/worktrees-hives/pull/79) | fix(cli): address CodeAnt/CodeRabbit review comments on PR #78 | agentic-workflow, tools | review-to-patch | Merged patch answering #78's bot review — extract as a pair with #78. |
| [#90](https://github.com/rmems/worktrees-hives/pull/90) | feat(python): lab run CLI single hypothesis unit | agentic-workflow | feature | 24 reviews / **62 threads**, 10 commits; heaviest thread traffic of the lab-CLI wave. Closes #80. |
| [#88](https://github.com/rmems/worktrees-hives/pull/88) | feat(python): lab findings JSON + Markdown contract | agentic-workflow, api | feature | 15 reviews / 10 threads; contract design (+764 lines, all-new). Closes #82. |
| [#103](https://github.com/rmems/worktrees-hives/pull/103) | feat(python): add Research Hive experiment contract | agentic-workflow, api | feature | 13 reviews on +932 lines; newest contract layer (merged 2026-08-13). Closes #92. |
| [#105](https://github.com/rmems/worktrees-hives/pull/105) | feat(python): aggregate discoveries report format (Markdown + table) | agentic-workflow, tools | feature | 10 reviews / 16 threads; freshest merge in the repo (2026-08-17 UTC). Closes #16. |

## Measured review density (raw, 2026-08-16)

| PR | Reviews | Threads | Comments | Size | Merged | Verdict |
|----|---------|---------|----------|------|--------|---------|
| #61 | 80 | 90 | 25 | +644/−0, 3 files | 2026-07-22 | shortlisted |
| #65 | 60 | 85 | 11 | +1736/−57, 22 files | 2026-07-16 | shortlisted |
| #63 | 53 | 40 | 16 | +1221/−0, 3 files | 2026-07-17 | shortlisted |
| #78 | 24 | 19 | 12 | +1036/−42, 7 files | 2026-08-07 | shortlisted |
| #90 | 24 | 62 | 12 | +1211/−8, 7 files | 2026-08-12 | shortlisted |
| #88 | 15 | 10 | 7 | +764/−0, 4 files | 2026-08-12 | shortlisted |
| #103 | 13 | 5 | 6 | +932/−1, 7 files | 2026-08-13 | shortlisted |
| #87 | 13 | 7 | 7 | +186/−106, 19 files | 2026-08-11 | rejected (toolchain-pin chore) |
| #105 | 10 | 16 | 6 | +927/−0, 6 files | 2026-08-17 | shortlisted |
| #89 | 9 | 18 | 7 | +973/−0, 3 files | 2026-08-12 | secondary (lab job model; add if the lab-CLI wave is extracted whole) |
| #104 | 8 | 10 | 10 | +241/−8, 5 files | 2026-08-15 | rejected (pure docs) |
| #79 | 4 | 1 | 5 | +133/−0, 3 files | 2026-08-03 | shortlisted (only as #78's patch pair) |

## Considered and rejected

- **`#87`** (pin Rust 1.97.1 / Python 3.14.7) — toolchain pin chore across 19 files;
  no domain trajectory.
- **`#104`** (Safe Issue → Verified Commit and PR workflows) — real review traffic but
  docs-only; fails the [pure-docs exclusion](_index.md#avoid-for-v0-training).
- **`#52`, `#67`, `#68`** — CI/Qodana plumbing without domain signal.
- The Issue-#N ladder `#53`–`#60`, `#62` (orchestrator, babysit cycle, watchlist,
  CI taxonomy, stack ordering, guardrails) is real feature work but was not measured
  this pass — re-score it if the extract wants more than 9 PRs.
