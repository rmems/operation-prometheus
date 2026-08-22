# worktrees-hives

<!-- index: [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives) | v0 extracted -->

**Repo**: [rmems/worktrees-hives](https://github.com/rmems/worktrees-hives)  
**Description**: Multi-agent hypothesis lab — agents/subagents in isolated git worktrees, mandatory JSON + Markdown findings, Python/Rust hybrid safety cage, never auto-merges  
**Language**: Python (+ Rust `wh-core`; `#65` is Rust via `language_by_pr`)  
**Status**: v0 **extracted** 2026-08-20 (issue [#26](https://github.com/rmems/operation-prometheus/issues/26) / shortlist [#30](https://github.com/rmems/operation-prometheus/issues/30)) — see [datasets/jsonl/worktrees-hives-v0.jsonl](../../datasets/jsonl/worktrees-hives-v0.jsonl)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#61](https://github.com/rmems/worktrees-hives/pull/61) | Issue #6: Claim issue → branch → worktree isolation | agentic-workflow | feature | Densest PR in the extract: 91 unique bodies (8 emitted). Closes #6. |
| [#63](https://github.com/rmems/worktrees-hives/pull/63) | Issue #8: Issue → PR workflow (never auto-merge) | agentic-workflow | feature | 75 unique bodies on the never-auto-merge invariant. Closes #8. |
| [#65](https://github.com/rmems/worktrees-hives/pull/65) | Foundation: R1–R3, R5, P1, H1, H3 (hybrid docs + Rust core + Python bridge) | ml-infra | feature | 87 unique bodies; hybrid-architecture cut. `language_by_pr` Rust. Closes #24–#42 (see details). |
| [#78](https://github.com/rmems/worktrees-hives/pull/78) | Wire discover/plan/babysit into the CLI | tools | review-to-patch | 17 unique bodies, 12 commits; paired with follow-up #79. Names #37. |
| [#79](https://github.com/rmems/worktrees-hives/pull/79) | fix(cli): address CodeAnt/CodeRabbit review comments on PR #78 | tools | review-to-patch | 2 unique bodies; kept as the patch half of the #78/#79 pair. |

## PR Details

### PR #61 — Claim issue → branch → worktree isolation

- **URL**: https://github.com/rmems/worktrees-hives/pull/61
- **Merged**: 2026-07-22
- **Commits**: 2
- **Files changed**: 3 (`claim.py` + tests; all Python)
- **Why high-signal**: Python policy glue over Rust `wh worktree`. `ClaimManager` validates owner/repo/job/branch/path/allowlist and refuses a local `git` subprocess fallback. Highest unique-body count in this extract (91).
- **Dataset bucket**: `feature` — agentic claim/isolation trajectory
- **Closes**: rmems/worktrees-hives#6

### PR #63 — Issue → PR workflow (never auto-merge)

- **URL**: https://github.com/rmems/worktrees-hives/pull/63
- **Merged**: 2026-07-17
- **Commits**: 3
- **Files changed**: 3 (`issue_to_pr.py` + tests)
- **Why high-signal**: Full issue-intake → worktree → branch push → `gh` PR open, with the never-auto-merge invariant enforced in code and in the PR body marker. 75 unique review bodies after bot filter.
- **Dataset bucket**: `feature` — safety-invariant orchestrator
- **Closes**: rmems/worktrees-hives#8

### PR #65 — Hybrid foundation (R1–R3, R5, P1, H1, H3)

- **URL**: https://github.com/rmems/worktrees-hives/pull/65
- **Merged**: 2026-07-16
- **Commits**: 8
- **Files changed**: 22 (+1736/−57) — Rust `wh-core`/`wh` plus Python bridge
- **Why high-signal**: Workspace, worktree manager, state store, allowlisted `git`/`gh` wrappers, JSON contract examples, and `WhClient` subprocess bridge. Mixed `.rs`/`.py`; card `language` is Python so `language_by_pr` pins this record to Rust. Body `Closes #24 #25 #26 #28 #30 #40 #42` only parses `#24` in `parse_linked_issue_numbers`; the rest are on the card.
- **Dataset bucket**: `feature` — hybrid-architecture foundation
- **Closes**: rmems/worktrees-hives#24, #25, #26, #28, #30, #40, #42 (card `linked_issues_by_pr`)

### PR #78 — Wire discover/plan/babysit into the CLI

- **URL**: https://github.com/rmems/worktrees-hives/pull/78
- **Merged**: 2026-08-07
- **Commits**: 12
- **Files changed**: 7 (Python CLI + tests)
- **Why high-signal**: Makes existing policy modules reachable as `discover` / `plan` / `babysit`. GitHub `bug` label would sniff `task_type` as bugfix; card forces `feature`. Names issue #37 without a close keyword.
- **Dataset bucket**: `review-to-patch` — 17 unique bodies, 8 emitted
- **Linked**: rmems/worktrees-hives#37 (card; not a GitHub close)

### PR #79 — Address CodeAnt/CodeRabbit comments on PR #78

- **URL**: https://github.com/rmems/worktrees-hives/pull/79
- **Merged**: 2026-08-03
- **Commits**: 2
- **Files changed**: 3
- **Why high-signal**: Owner-allowlist gate, incomplete-listing failure, `--max-fixes` ceiling, richer babysit envelope. Low unique-body count (2); kept as the patch half of the #78/#79 pair, not as a yield leader.
- **Dataset bucket**: `review-to-patch`
- **Closes**: — (follow-up to #78)

## Measured review-signal yield (2026-08-20)

Counted by replaying each PR's `reviews`, `review_comments`, and `issue_comments` through
[`is_bot_user`](../../scripts/lib/bots.py) and
[`extract_review_signals`](../../scripts/lib/normalize.py)
(hard cap `max_items=8`). Pipeline modules were not edited. Unique bodies are
`extract_review_signals(..., max_items=10000)`.

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #61 | 91 | 8 | 91 | **extracted** (feature) |
| #65 | 87 | 8 | 87 | **extracted** (feature; hybrid foundation) |
| #63 | 75 | 8 | 75 | **extracted** (feature) |
| #78 | 17 | 8 | 17 | **extracted** (review-to-patch; pair with #79) |
| #79 | 2 | 2 | 2 | **extracted** (review-to-patch; #78 patch pair) |

Live `list_merged_prs.py --repo rmems/worktrees-hives` confirmed all five as merged.

## Deferred (lab-CLI wave)

Not needed to hit a 5-PR shortlist; leave for a later extract:

- [#90](https://github.com/rmems/worktrees-hives/pull/90) lab run CLI single hypothesis unit
- [#88](https://github.com/rmems/worktrees-hives/pull/88) lab findings JSON + Markdown contract
- [#103](https://github.com/rmems/worktrees-hives/pull/103) Research Hive experiment contract
- [#105](https://github.com/rmems/worktrees-hives/pull/105) aggregate discoveries report format
- [#89](https://github.com/rmems/worktrees-hives/pull/89) lab job model (secondary if that wave is extracted whole)

## Considered and rejected

- **`#87`** (pin Rust 1.97.1 / Python 3.14.7) — toolchain pin chore across 19 files;
  no domain trajectory.
- **`#104`** (Safe Issue → Verified Commit and PR workflows) — real review traffic but
  docs-only; fails the [pure-docs exclusion](_index.md#avoid-for-v0-training).
- **`#52`, `#67`, `#68`** — CI/Qodana plumbing without domain signal.
- The Issue-#N ladder `#53`–`#60`, `#62` (orchestrator, babysit cycle, watchlist,
  CI taxonomy, stack ordering, guardrails) is real feature work but was not measured
  this pass — re-score it if the extract wants more than 5 PRs.
