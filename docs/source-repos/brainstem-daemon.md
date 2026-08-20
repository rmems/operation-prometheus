# brainstem-daemon

<!-- index: [Limen-Neural/brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon) | v0 extracted -->

**Repo**: [Limen-Neural/brainstem-daemon](https://github.com/Limen-Neural/brainstem-daemon)  
**Description**: SNN runtime daemon (ServiceRegistry, optional corpus-ipc/ZMQ, neuron-count validation)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-08-20, issue [#28](https://github.com/rmems/operation-prometheus/issues/28), Limen Wave B+ pilot) — see [datasets/jsonl/brainstem-daemon-v0.jsonl](../../datasets/jsonl/brainstem-daemon-v0.jsonl)  
**Metadata card**: [datasets/cards/brainstem-daemon-v0.json](../../datasets/cards/brainstem-daemon-v0.json)

> Counts below are **raw** GitHub API totals (*pre* bot-filter). Pipeline yield
> is measured at extraction time.

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#8](https://github.com/Limen-Neural/brainstem-daemon/pull/8) | feat: resolve open issues #4, #5, #6, #7 | infra | feature | 215 raw reviews / 8 unique; ServiceRegistry library split (plus CI/license). |
| [#24](https://github.com/Limen-Neural/brainstem-daemon/pull/24) | feat: temporary corpus-ipc decoupling (issues #10, #11, #12, #14) | api | review-to-patch | 56 raw / 8 unique; local ingress/egress traits. |
| [#25](https://github.com/Limen-Neural/brainstem-daemon/pull/25) | Fallible BrainstemDaemon construction with neuron-count validation | snn | repair | 18 raw / 8 unique; `try_new` instead of panic. |
| [#3](https://github.com/Limen-Neural/brainstem-daemon/pull/3) | Migrate daemon to corpus-ipc and neuromod v0.4.0 | snn | feature | 2 unique; ZMQ ingress/egress + `with_dimensions`. |

## PR Details

### PR #8 — feat: resolve open issues #4, #5, #6, #7

- **URL**: https://github.com/Limen-Neural/brainstem-daemon/pull/8
- **Merged**: 2026-07-01
- **Commits**: 22
- **Files changed**: 14
- **Why high-signal**: Introduces config-driven `ServiceRegistry` and a `BrainstemDaemon` library runtime (#5) while also landing CI (#6) and dual license (#7). Kept for the domain runtime split, not as a CI-only monster.
- **Dataset bucket**: `feature`
- **Closes**: #4, #5, #6, #7
- **Card**: `task_type_by_pr` = `refactor` (beats `feat:`)

### PR #24 — feat: temporary corpus-ipc decoupling

- **URL**: https://github.com/Limen-Neural/brainstem-daemon/pull/24
- **Merged**: 2026-07-04
- **Commits**: 25
- **Files changed**: 12
- **Why high-signal**: Local `IngressPacket` / `SpikeEvent` traits and a stub backend so `corpus-ipc`+`zmq` can be optional.
- **Dataset bucket**: `review-to-patch`
- **Provenance**: issues #10, #11, #12, #14 (card `linked_issues_by_pr`; body has no close keywords)

### PR #25 — Fallible BrainstemDaemon construction with neuron-count validation

- **URL**: https://github.com/Limen-Neural/brainstem-daemon/pull/25
- **Merged**: 2026-07-11
- **Files changed**: 3
- **Why high-signal**: `try_new` / `validate_neuron_count` so `lif_count + izh_count > u16::MAX` is an error, not a process abort.
- **Dataset bucket**: `repair`

### PR #3 — Migrate daemon to corpus-ipc and neuromod v0.4.0

- **URL**: https://github.com/Limen-Neural/brainstem-daemon/pull/3
- **Merged**: 2026-04-22
- **Files changed**: 3
- **Why high-signal**: Wires `SpikingNetwork::with_dimensions` and corpus-ipc ZMQ PUB/SUB.
- **Dataset bucket**: `feature`

## Measured review density (raw, 2026-08-20)

| PR | Reviews | Threads | Yield (unique) | Size | Verdict |
|----|---------|---------|----------------|------|---------|
| #8 | 215 | 246 | 8 | +2380/−837, 14 files | shortlisted |
| #24 | 56 | 73 | 8 | +673/−158, 12 files | shortlisted |
| #25 | 18 | 20 | 8 | +109/−13, 3 files | shortlisted |
| #3 | 4 | 8 | 2 | +116/−44, 3 files | shortlisted |
| #1 | 1 | 0 | 0 | 100 files, mostly `target/` | rejected |
| #27 | 2 | 2 | 0 | empty file list | skipped |

## Considered and rejected

- **`#1`** (`feat: upgrade`) — committed `target/` build artifacts.
- **`#27`** Aikido path-traversal “fix” with no files in the collected record.
- Docs / qodana (`#33`, `#26`, `#28`)
- **`#34`** Cargo profiles / README claim cleanup
