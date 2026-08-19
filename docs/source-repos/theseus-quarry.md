# Theseus-Quarry

<!-- index: [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry) | v0 extracted -->

**Repo**: [rmems/Theseus-Quarry](https://github.com/rmems/Theseus-Quarry)  
**Description**: Crypto-mining telemetry extraction for neuromorphic-computing research (miner HTTP APIs, JSONL telemetry, GPU signaling)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-19, issue [#27](https://github.com/rmems/operation-prometheus/issues/27), v0.6 Fleet extracts) — see [datasets/jsonl/theseus-quarry-v0.jsonl](../../datasets/jsonl/theseus-quarry-v0.jsonl)  
**Metadata card**: [datasets/cards/theseus-quarry-v0.json](../../datasets/cards/theseus-quarry-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time. Small repo:
> 9 merged PRs total, 5 shortlisted for extraction.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#13](https://github.com/rmems/Theseus-Quarry/pull/13) | Telemetry: Migrate MinerPerf collection to HTTP APIs | telemetry | feature | Densest: 35 reviews / 20 threads; +650/−841 across 14 files — a real migration, not additive. Closes #5. |
| [#9](https://github.com/rmems/Theseus-Quarry/pull/9) | Port GPU thermal throttling process signaling to telemetry-collector | telemetry, gpu-compute | feature | 17 reviews / 31 threads, 12 commits; thermal-safety semantics under review. Closes #4. |
| [#12](https://github.com/rmems/Theseus-Quarry/pull/12) | feat(telemetry): align miner API ports and node RPC endpoints | telemetry, config | repair | 14 reviews / 13 threads across 12 files; endpoint-correctness fix wave. Closes #7. |
| [#11](https://github.com/rmems/Theseus-Quarry/pull/11) | feat(telemetry): implement file rotation for JSONL telemetry | telemetry | feature | 10 reviews / 18 threads on a surgical +46/−26 diff; high thread-to-line ratio. Closes #6. |
| [#8](https://github.com/rmems/Theseus-Quarry/pull/8) | arch: remove theseus-mining supervisor and migrate gpu_scheduler | telemetry, infra | repair | 28 reviews / 27 threads; −5442-line architectural amputation across 24 files. Closes #3. |

## PR Details

### PR #13 — Telemetry: Migrate MinerPerf collection to HTTP APIs

- **URL**: https://github.com/rmems/Theseus-Quarry/pull/13
- **Merged**: 2026-08-12
- **Commits**: 3
- **Files changed**: 14
- **Why high-signal**: Deletes stdout scraping from `mining-telemetry-core` and polls BzMiner / XMRig / OneZeroMiner HTTP APIs for `MinerPerf`. Real migration (−841 lines) with the densest review volume in the repo. Resolves #5.
- **Dataset bucket**: `feature` — HTTP MinerPerf collection path
- **Closes**: rmems/Theseus-Quarry#5

### PR #9 — Port GPU thermal throttling process signaling to telemetry-collector

- **URL**: https://github.com/rmems/Theseus-Quarry/pull/9
- **Merged**: 2026-08-11
- **Commits**: 12
- **Files changed**: 8
- **Why high-signal**: Adds `process_governor` so telemetry-collector SIGSTOP/SIGCONT-s known miner processes when GPU thermal/VRAM limits trip. 12-commit review loop on thermal-safety semantics. Resolves #4.
- **Dataset bucket**: `feature` — GPU thermal process signaling
- **Closes**: rmems/Theseus-Quarry#4

### PR #12 — feat(telemetry): align miner API ports and node RPC endpoints

- **URL**: https://github.com/rmems/Theseus-Quarry/pull/12
- **Merged**: 2026-08-07
- **Commits**: 6
- **Files changed**: 12
- **Why high-signal**: Replaces hardcoded loopback miner/node URLs with CLI/env-configurable endpoints and adds `check_port_free` preflight. Endpoint-correctness repair across 12 files. Resolves #7.
- **Dataset bucket**: `repair` — miner API port and node RPC alignment
- **Closes**: rmems/Theseus-Quarry#7

### PR #11 — feat(telemetry): implement file rotation for JSONL telemetry

- **URL**: https://github.com/rmems/Theseus-Quarry/pull/11
- **Merged**: 2026-08-07
- **Commits**: 7
- **Files changed**: 4
- **Why high-signal**: Daily `rolling-file` rotation with 7-day retention on a surgical +46/−26 change; high review-thread-to-line ratio. Resolves #6.
- **Dataset bucket**: `feature` — JSONL telemetry file rotation
- **Closes**: rmems/Theseus-Quarry#6

### PR #8 — arch: remove theseus-mining supervisor and migrate gpu_scheduler

- **URL**: https://github.com/rmems/Theseus-Quarry/pull/8
- **Merged**: 2026-08-05
- **Commits**: 5
- **Files changed**: 24
- **Why high-signal**: Removes the `theseus-mining` supervisor crate (−5442 lines) and moves `gpu_scheduler` into `telemetry-collector` so thermal governance survives without the supervisor. Closes #3.
- **Dataset bucket**: `repair` — architectural amputation plus scheduler migration
- **Closes**: rmems/Theseus-Quarry#3

## Measured review density (raw, 2026-08-16)

| PR | Reviews | Threads | Comments | Size | Merged | Verdict |
|----|---------|---------|----------|------|--------|---------|
| #13 | 35 | 20 | 8 | +650/−841, 14 files | 2026-08-12 | shortlisted |
| #8 | 28 | 27 | 8 | +71/−5442, 24 files | 2026-08-05 | shortlisted |
| #9 | 17 | 31 | 18 | +448/−22, 8 files | 2026-08-11 | shortlisted |
| #12 | 14 | 13 | 6 | +132/−62, 12 files | 2026-08-07 | shortlisted |
| #18 | 13 | 5 | 5 | +390/−12, 10 files | 2026-08-13 | deferred |
| #16 | 13 | 5 | 6 | +143/−0, 4 files | 2026-08-12 | deferred |
| #11 | 10 | 18 | 6 | +46/−26, 4 files | 2026-08-07 | shortlisted |

## Deferred (not rejected)

- **`#16`** (Quality: Cargo profiles + REVIEW.md) — borderline config/docs. Keep for a later validation-bucket row, not this v0 extract.
- **`#18`** (Telemetry: SRBMiner-Multi HTTP MinerPerf parser) — later second-miner extension of the #13 HTTP path. Revisit after v0.

## Considered and rejected

- **`#1`** (self-hosted Rust + dual Qodana + Docker/devcontainer + qlty + Codacy) —
  bulk CI-modernization monster without domain signal; excluded under
  [_index.md](_index.md#avoid-for-v0-training).
- **`#2`** (fix PR bot findings + Cursor Cloud Docker / AGENTS.md) — mixed
  bot-finding fixups and agent-config docs; no coherent issue-anchored trajectory.
- **`#20`** (ownership boundaries docs) — open, unmerged, and docs-only.
