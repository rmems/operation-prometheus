# thalamic-relay

<!-- index: [rmems/thalamic-relay](https://github.com/rmems/thalamic-relay) | v0 extracted -->

**Repo**: [rmems/thalamic-relay](https://github.com/rmems/thalamic-relay)  
**Description**: GPU-safety supervisor / thalamic relay (thermal and power brakes, IPC, neuromod + silicon-bridge wiring)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#29](https://github.com/rmems/operation-prometheus/issues/29), Wave C pilot) — see [datasets/jsonl/thalamic-relay-v0.jsonl](../../datasets/jsonl/thalamic-relay-v0.jsonl)  
**Metadata card**: [datasets/cards/thalamic-relay-v0.json](../../datasets/cards/thalamic-relay-v0.json)

> Counts below are **raw** GitHub API totals (`reviews` / review threads / issue
> comments — *pre* bot-filter). Pipeline yield (`is_bot_user` +
> `extract_review_signals`, cap 8) is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#20](https://github.com/rmems/thalamic-relay/pull/20) | feat: integrate GPU safety monitoring into main supervisor loop | gpu-compute | feature | 40 kept / 5 emitted (duplicate aggregate review summary dropped). Wires `check_safety` into the loop; closes #14 / #12. |
| [#23](https://github.com/rmems/thalamic-relay/pull/23) | fix: harden GPU brake recovery on safety PR | gpu-compute | repair | 33 kept / 5 emitted. Fresh telemetry after `release_task` so the brake cannot lift into a still-critical GPU. |
| [#22](https://github.com/rmems/thalamic-relay/pull/22) | test: increase coverage for supervisor + IPC paths | systems | validation | 52 kept / 1 emitted (3 raw variants deduped to the richest UDP-sleep-flakiness signal). 8→17 tests on UDP/IPC + metrics; closes #13. |

## PR Details

### PR #20 — feat: integrate GPU safety monitoring into main supervisor loop

- **URL**: https://github.com/rmems/thalamic-relay/pull/20
- **Merged**: 2026-07-11
- **Commits**: 9
- **Files changed**: 6
- **Why high-signal**: Replaces dead `check_firmware` / `check_rails` stubs with threshold-based `SafetyStatus` (thermal >85°C, power >350W) and rate-limited emergency brake in the supervisor loop.
- **Dataset bucket**: `feature`
- **Closes**: rmems/thalamic-relay#14, #12

### PR #23 — fix: harden GPU brake recovery on safety PR

- **URL**: https://github.com/rmems/thalamic-relay/pull/23
- **Merged**: 2026-07-16
- **Commits**: 21
- **Files changed**: 7
- **Why high-signal**: Review-driven repair: post-release safety check was using stale telemetry while the brake was still applied. Dense GPU-label review loop on `src/gpu.rs` / `src/main.rs`.
- **Dataset bucket**: `repair`

### PR #22 — test: increase coverage for supervisor + IPC paths

- **URL**: https://github.com/rmems/thalamic-relay/pull/22
- **Merged**: 2026-07-10
- **Commits**: 2
- **Files changed**: 2
- **Why high-signal**: Highest kept-signal count in the cluster; surgical tests for `process_udp_messages` and `RelayMetrics` (invalid JSON must not panic).
- **Dataset bucket**: `validation`
- **Closes**: rmems/thalamic-relay#13

## Measured review-signal yield

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #22 | 52 | 1 | 1 | shortlisted (3 raw duplicates of one UDP-sleep-flakiness signal deduped) |
| #20 | 40 | 5 | 5 | shortlisted (duplicate aggregate review summary dropped) |
| #23 | 33 | 5 | 5 | shortlisted |
| #18 | 25 | 8 | 8 | deferred (CLI, not GPU-safety) |
| #36 | 0 | 0 | 0 | dropped (0 kept signals) |

## Deferred (not rejected)

- **`#18`** (CLI clap argument parsing, 25 kept) — real code, high yield, outside the GPU-safety cluster. Revisit after Wave C pilot.

## Considered and rejected

- **`#36`** (supervisor/IPC/GPU software-only coverage tests) — listed as a live candidate but 0 kept review signals after bot filter.
- **`#35`** — post-transfer hygiene (Limen-Neural → rmems).
- **`#33`**, **`#30`**, **`#21`** — changelog / MSRV docs / acronyms docs.
