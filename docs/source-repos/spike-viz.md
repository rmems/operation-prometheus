# spike-viz

<!-- index: [rmems/spike-viz](https://github.com/rmems/spike-viz) | v0 extracted -->

**Repo**: [rmems/spike-viz](https://github.com/rmems/spike-viz)  
**Description**: CPU spike visualization — axon-encoder export contract, schema loaders, raster PNG rendering  
**Language**: Python  
**Status**: v0 **extracted** (2026-08-20, issue [#29](https://github.com/rmems/operation-prometheus/issues/29), Wave C pilot) — see [datasets/jsonl/spike-viz-v0.jsonl](../../datasets/jsonl/spike-viz-v0.jsonl)  
**Metadata card**: [datasets/cards/spike-viz-v0.json](../../datasets/cards/spike-viz-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time. Small repo:
> 4 merged PRs total; 3 domain PRs extracted.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#24](https://github.com/rmems/spike-viz/pull/24) | feat: CPU raster renderer (sparse/dense → PNG) | visualization | feature | 4 kept / 2 emitted. `render_raster()` on CPU. Closes #9. |
| [#23](https://github.com/rmems/spike-viz/pull/23) | fix: address PR #22 review comments | io | review-to-patch | 10 kept / 8 emitted. Explicit follow-up to #22 (cannot reopen). |
| [#22](https://github.com/rmems/spike-viz/pull/22) | feat: export contract, schema loaders, package skeleton | io | feature | 7 kept / 5 emitted (2 follow-up/status notices for #23 dropped). Closes #6 / #8 / #10. |

## PR Details

### PR #24 — feat: CPU raster renderer (sparse/dense → PNG)

- **URL**: https://github.com/rmems/spike-viz/pull/24
- **Merged**: 2026-08-02
- **Commits**: 5
- **Files changed**: 5
- **Why high-signal**: Adds `render_raster()` (time × neuron grayscale PNG via Pillow). CPU-only; 7 new tests.
- **Dataset bucket**: `feature`
- **Closes**: rmems/spike-viz#9

### PR #23 — fix: address PR #22 review comments

- **URL**: https://github.com/rmems/spike-viz/pull/23
- **Merged**: 2026-07-26
- **Commits**: 4
- **Files changed**: 8
- **Why high-signal**: #22 merged before bot review landed; this PR is the review-to-patch half (fail-loud meta, geometry, dtypes, schema version, license).
- **Dataset bucket**: `review-to-patch`

### PR #22 — feat: export contract, schema loaders, package skeleton

- **URL**: https://github.com/rmems/spike-viz/pull/22
- **Merged**: 2026-07-25
- **Commits**: 1
- **Files changed**: 15
- **Why high-signal**: Package skeleton plus `load_sparse` / `load_dense` / `load_axon_export` and the axon-encoder golden fixture.
- **Dataset bucket**: `feature`
- **Closes**: rmems/spike-viz#6, #8, #10

## Measured review-signal yield

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #23 | 10 | 8 | 8 | shortlisted (pair with #22) |
| #22 | 7 | 5 | 5 | shortlisted (2 follow-up/status notices for #23 dropped) |
| #24 | 4 | 2 | 2 | shortlisted |
| #21 | 0 | 0 | 0 | dropped (docs-only) |

## Considered and rejected

- **`#21`** (`docs: charter, AGENTS.md, REVIEW.md`) — docs-only, 0 kept signals.
