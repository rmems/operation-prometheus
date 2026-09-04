# agoge-forger

<!-- index: [rmems/agoge-forger](https://github.com/rmems/agoge-forger) | v0 extracted -->

**Repo**: [rmems/agoge-forger](https://github.com/rmems/agoge-forger)  
**Description**: Local fine-tuning forge (QLoRA/LoRA, JSONL contracts, adapter merge)  
**Language**: Python  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/agoge-forger-v0.jsonl](../../datasets/jsonl/agoge-forger-v0.jsonl)  
**Metadata card**: [datasets/cards/agoge-forger-v0.json](../../datasets/cards/agoge-forger-v0.json)

> Yield below is pipeline yield (`is_bot_user` + `extract_review_signals`).

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#120](https://github.com/rmems/agoge-forger/pull/120) | feat(data,eval): land hardened frozen-contract tree and Qlty Bandit gate | ml-infra | feature | 7 kept. Frozen-split / paired-eval tree. Closes #119. |
| [#67](https://github.com/rmems/agoge-forger/pull/67) | fix(train): migrate SFTTrainer to TRL 1.x SFTConfig | training | repair | 9 kept / 8 emitted. Closes #63 / #66. |
| [#85](https://github.com/rmems/agoge-forger/pull/85) | fix: harden empty JSONL and non-string message content | ml-infra | repair | 5 kept. Closes #65. |
| [#86](https://github.com/rmems/agoge-forger/pull/86) | fix: stop passing safe_serialization to merged model save | training | repair | 2 kept. Closes #68. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #120 | 7 | 7 | 7 | shortlisted |
| #67 | 9 | 8 | 8 | shortlisted |
| #85 | 5 | 5 | 5 | shortlisted |
| #86 | 2 | 2 | 2 | shortlisted (repair pair with #85) |
| #91 | 0 | 0 | 0 | dropped (0 yield) |
| #84 | 0 | 0 | 0 | dropped (0 yield) |
| #74 | 0 | 0 | 0 | dropped (0 yield) |
| #73 | 0 | 0 | 0 | dropped (0 yield) |

## Considered and rejected

- **`#91`, `#84`, `#74`, `#73`** — domain titles but 0 kept review signals after bot filter.
- Dependabot / ruff / Qodana / docs-only PRs — skip list.
