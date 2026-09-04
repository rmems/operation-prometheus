# silicon-hdl

<!-- index: [rmems/silicon-hdl](https://github.com/rmems/silicon-hdl) | v0 extracted -->

**Repo**: [rmems/silicon-hdl](https://github.com/rmems/silicon-hdl)  
**Description**: SystemVerilog SNN core/SoC (INIT_FILE RAMs, Basys3, multiplexed LIF PE)  
**Language**: SystemVerilog  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/silicon-hdl-v0.jsonl](../../datasets/jsonl/silicon-hdl-v0.jsonl)  
**Metadata card**: [datasets/cards/silicon-hdl-v0.json](../../datasets/cards/silicon-hdl-v0.json)

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#81](https://github.com/rmems/silicon-hdl/pull/81) | feat(soc): time-multiplex N=16 LIF PE | hdl | feature | 9 kept / 8 emitted. Closes #61. |
| [#51](https://github.com/rmems/silicon-hdl/pull/51) | feat(core): INIT_FILE $readmemh for RAMs — E1 | hdl | feature | 24 kept. Closes #38. |
| [#52](https://github.com/rmems/silicon-hdl/pull/52) | feat(soc): E2 Basys3 INIT_FILE + mem add_files | hdl | feature | 5 kept. Closes #39. |
| [#15](https://github.com/rmems/silicon-hdl/pull/15) | fix(gh-14): address unresolved bot review from PR #1/#2 | hdl | review-to-patch | 46 kept. Closes #14. |
| [#11](https://github.com/rmems/silicon-hdl/pull/11) | Clean up basys3.xdc, fix LifNeuron spike-reset | hdl | repair | 48 kept. Closes #4 / #7. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #81 | 9 | 8 | 8 | shortlisted |
| #51 | 24 | 8 | 8 | shortlisted |
| #52 | 5 | 5 | 5 | shortlisted |
| #15 | 46 | 8 | 8 | shortlisted |
| #11 | 48 | 8 | 8 | shortlisted |
| #78 | 0 | 0 | 0 | dropped (0 yield) |
| #80 | 11 | 8 | 8 | dropped (UART testbenches; kept SoC/core pair instead) |

## Considered and rejected

- **`#78`** — gated LIF/STDP + Vivado, 0 kept signals.
- **`#80`** — Verilator UART TBs; surplus to the 5-PR cap.
- Docs, Vivado/CI-only, license, CLAUDE.md — skip list.
