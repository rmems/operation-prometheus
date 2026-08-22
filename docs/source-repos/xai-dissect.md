# xai-dissect

<!-- index: [rmems/xai-dissect](https://github.com/rmems/xai-dissect) | v0 extracted -->

**Repo**: [rmems/xai-dissect](https://github.com/rmems/xai-dissect)  
**Description**: Grok-1 shard dissection, coverage manifests, and grok-ozempic export / quant-plan contract  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#29](https://github.com/rmems/operation-prometheus/issues/29), Wave C pilot) — see [datasets/jsonl/xai-dissect-v0.jsonl](../../datasets/jsonl/xai-dissect-v0.jsonl)  
**Metadata card**: [datasets/cards/xai-dissect-v0.json](../../datasets/cards/xai-dissect-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#32](https://github.com/rmems/xai-dissect/pull/32) | Define xai-dissect export contract for grok-ozempic | export | feature | 30 kept / 8 emitted. Domain anchor: `quant-plan` bundle + handoff docs. Closes #21. |
| [#34](https://github.com/rmems/xai-dissect/pull/34) | Export conversion-ready Grok-1 tensor manifest for SAAQ sprint | export | feature | 10 kept / 7 emitted. Markdown conversion manifest + #23 acceptance tests. Closes #23. |
| [#24](https://github.com/rmems/xai-dissect/pull/24) | Implement strict Grok-1 coverage manifest validation | ml-infra | feature | 28 kept / 7 emitted. Fail-closed 770-tensor coverage. Closes #22. |
| [#36](https://github.com/rmems/xai-dissect/pull/36) | Complete Grok-1 planning/report PR surfaces | quantization | feature | 15 kept / 8 emitted. Pilot-plan, route-preservation, GO/NO-GO. Closes #25–#29, #31. |

## PR Details

### PR #32 — Define xai-dissect export contract for grok-ozempic

- **URL**: https://github.com/rmems/xai-dissect/pull/32
- **Merged**: 2026-05-26
- **Commits**: 4
- **Files changed**: 17 (+2405/−59)
- **Why high-signal**: Documents the grok-ozempic handoff and lands `quant-plan` conversion/quant artifacts with snapshot tests. Not CI.
- **Dataset bucket**: `feature`
- **Closes**: rmems/xai-dissect#21

### PR #34 — Export conversion-ready Grok-1 tensor manifest for SAAQ sprint

- **URL**: https://github.com/rmems/xai-dissect/pull/34
- **Merged**: 2026-05-26
- **Commits**: 8
- **Files changed**: 3 (all `.rs`; documentation label is misleading)
- **Why high-signal**: Adds conversion-manifest Markdown plus the three #23 acceptance tests (`CandidateSaaqEmbedding`, unresolved projections, unknown passthrough).
- **Dataset bucket**: `feature`
- **Closes**: rmems/xai-dissect#23

### PR #24 — Implement strict Grok-1 coverage manifest validation

- **URL**: https://github.com/rmems/xai-dissect/pull/24
- **Merged**: 2026-05-25
- **Commits**: 10
- **Files changed**: 7
- **Why high-signal**: Fail-closed coverage for complete 770-tensor inventories; deterministic `grok1-coverage.json`.
- **Dataset bucket**: `feature`
- **Closes**: rmems/xai-dissect#22

### PR #36 — Complete Grok-1 planning/report PR surfaces

- **URL**: https://github.com/rmems/xai-dissect/pull/36
- **Merged**: 2026-05-27
- **Commits**: 6
- **Files changed**: 17
- **Why high-signal**: Pilot-plan and route-preservation CLI/report surfaces plus GO/NO-GO gate docs; still structural analysis, not a quant runtime.
- **Dataset bucket**: `feature`
- **Closes**: rmems/xai-dissect#25, #26, #27, #28, #29, #31

## Measured review-signal yield

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #32 | 30 | 8 | 8 | shortlisted (domain anchor) |
| #24 | 28 | 7 | 7 | shortlisted |
| #36 | 15 | 8 | 8 | shortlisted |
| #34 | 10 | 7 | 7 | shortlisted |
| #20 | 8 | 8 | 8 | deferred |
| #16 | 6 | 6 | 6 | deferred |
| #48 | — | — | — | **excluded** bulk CI (Qodana/Codecov/Sentry) |

## Deferred (not rejected)

- **`#20`**, **`#16`**, **`#6`**, **`#1`** — earlier inventory / router / CLI layers. Revisit after this export-contract v0.

## Considered and rejected

- **`#48`** (`ci: full GitHub Actions with Codecov, Qodana, optional Sentry`) — 137-review CI-modernization monster; excluded under the bulk-CI rule despite density.
- **`#53`**, **`#37`** — docs-only gates / handoff.
- **`#51`** — relicense.
- **`#50`** — Sentry project wiring.
