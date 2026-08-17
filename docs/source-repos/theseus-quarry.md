# Theseus-Quarry

<!-- index: [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry) | shortlist drafted -->

**Repo**: [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry)  
**Description**: Crypto-mining telemetry extraction for neuromorphic-computing research (miner HTTP APIs, JSONL telemetry, GPU signaling)  
**Language**: Rust  
**Status**: shortlist **drafted** (2026-08-16 live scan, issue [#30](https://github.com/rmems/operation-prometheus/issues/30)) — not extracted; v0.6 telemetry priority

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time. Small repo:
> 9 merged PRs total, 7 shortlisted.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#13](https://github.com/rmems/Theseus-Quarry/pull/13) | Telemetry: Migrate MinerPerf collection to HTTP APIs | telemetry | feature | Densest: 35 reviews / 20 threads; +650/−841 across 14 files — a real migration, not additive. Closes #5. |
| [#8](https://github.com/rmems/Theseus-Quarry/pull/8) | arch: remove theseus-mining supervisor and migrate gpu_scheduler | telemetry, infra | repair | 28 reviews / 27 threads; −5442-line architectural amputation across 24 files. Closes #3. |
| [#9](https://github.com/rmems/Theseus-Quarry/pull/9) | Port GPU thermal throttling process signaling to telemetry-collector | telemetry, gpu-compute | feature | 17 reviews / 31 threads, 12 commits; thermal-safety semantics under review. Closes #4. |
| [#12](https://github.com/rmems/Theseus-Quarry/pull/12) | feat(telemetry): align miner API ports and node RPC endpoints | telemetry, config | repair | 14 reviews / 13 threads across 12 files; endpoint-correctness fix wave. Closes #7. |
| [#18](https://github.com/rmems/Theseus-Quarry/pull/18) | Telemetry: SRBMiner-Multi HTTP MinerPerf parser | telemetry | feature | 13 reviews; newest merge (2026-08-13), extends the #13 HTTP path to a second miner. Closes #14. |
| [#11](https://github.com/rmems/Theseus-Quarry/pull/11) | feat(telemetry): implement file rotation for JSONL telemetry | telemetry | feature | 10 reviews / 18 threads on a surgical +46/−26 diff; high thread-to-line ratio. Closes #6. |
| [#16](https://github.com/rmems/Theseus-Quarry/pull/16) | Quality: Cargo profiles + REVIEW.md | testing, config | validation | 13 reviews; borderline (part config, part docs) — keep only if the extract wants a validation-bucket row. Closes #10. |

## Measured review density (raw, 2026-08-16)

| PR | Reviews | Threads | Comments | Size | Merged | Verdict |
|----|---------|---------|----------|------|--------|---------|
| #13 | 35 | 20 | 8 | +650/−841, 14 files | 2026-08-12 | shortlisted |
| #8 | 28 | 27 | 8 | +71/−5442, 24 files | 2026-08-05 | shortlisted |
| #9 | 17 | 31 | 18 | +448/−22, 8 files | 2026-08-11 | shortlisted |
| #12 | 14 | 13 | 6 | +132/−62, 12 files | 2026-08-07 | shortlisted |
| #18 | 13 | 5 | 5 | +390/−12, 10 files | 2026-08-13 | shortlisted |
| #16 | 13 | 5 | 6 | +143/−0, 4 files | 2026-08-12 | shortlisted (borderline) |
| #11 | 10 | 18 | 6 | +46/−26, 4 files | 2026-08-07 | shortlisted |

## Considered and rejected

- **`#1`** (self-hosted Rust + dual Qodana + Docker/devcontainer + qlty + Codacy) —
  bulk CI-modernization monster without domain signal; excluded under
  [_index.md](_index.md#avoid-for-v0-training).
- **`#2`** (fix PR bot findings + Cursor Cloud Docker / AGENTS.md) — mixed
  bot-finding fixups and agent-config docs; no coherent issue-anchored trajectory.
- **`#20`** (ownership boundaries docs) — open, unmerged, and docs-only.
