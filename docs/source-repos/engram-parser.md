# engram-parser

<!-- index: [rmems/engram-parser](https://github.com/rmems/engram-parser) | v0 extracted -->

**Repo**: [rmems/engram-parser](https://github.com/rmems/engram-parser)  
**Description**: Zero-dep GGUF parser and per-expert MoE weight extractor (wire layouts, not dequant/kernels)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#29](https://github.com/rmems/operation-prometheus/issues/29), Wave C pilot) — see [datasets/jsonl/engram-parser-v0.jsonl](../../datasets/jsonl/engram-parser-v0.jsonl)  
**Metadata card**: [datasets/cards/engram-parser-v0.json](../../datasets/cards/engram-parser-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time. Recent
> history is Dependabot-dominated (20+ of 35 merged).

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#44](https://github.com/rmems/engram-parser/pull/44) | feat: GGUF v3 parser, IQ wire layouts, and T1 large MoE pilots | ml-infra | feature | 8 kept / 8 emitted. Completes #7; 32 commits; +3017/−295 across 19 files. |

## PR Details

### PR #44 — feat: GGUF v3 parser, IQ wire layouts, and T1 large MoE pilots

- **URL**: https://github.com/rmems/engram-parser/pull/44
- **Merged**: 2026-08-07
- **Commits**: 32
- **Files changed**: 19
- **Why high-signal**: Zero-dep GGUF v3 layout parse + MoE raw expert extract; wire-type labels and packed `byte_len` (not GGML dequant). Path-gated T1 pilots. MSRV 1.87 → 1.97.1.
- **Dataset bucket**: `feature`
- **Closes**: rmems/engram-parser#7 (originally filed on Limen-Neural/engram-parser)

## Measured review-signal yield

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #44 | 8 | 8 | 8 | shortlisted |
| #17 | 37 | 8 | 8 | dropped (Docker + GH Actions CI) |
| #57 | 5 | 5 | 5 | dropped (docs-only) |
| #1 | 3 | 3 | 3 | dropped (`target/` artifact noise) |
| #21 | 2 | 2 | 2 | dropped (MSRV CI) |
| #23 | 1 | 1 | 1 | dropped (repo-hygiene) |

## Considered and rejected

- **`#1`** (zero-dep GGUF parser + MoE extractor) — founding domain PR, but the merged tree commits `target/` build artifacts (~300 extra files); same noise class as myelin-accelerator#2.
- **`#17`** — combine Docker/GHCR + harden GitHub Actions (CI).
- **`#23`** — duplicated source layout / `.gitignore` hygiene.
- **`#21`** — MSRV policy CI.
- **`#57`** — docs-only reverse of #10.
- **`#40`** — Qodana-only.
- **`#51`** — post-transfer hygiene.
- Dependabot bumps (`#24`–`#56` range) — dependency noise.
