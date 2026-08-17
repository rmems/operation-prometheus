# myelin-accelerator

<!-- index: [rmems/myelin-accelerator](https://github.com/rmems/myelin-accelerator) | v0 extracted -->

**Repo**: [rmems/myelin-accelerator](https://github.com/rmems/myelin-accelerator)  
**Description**: CUDA kernels and bitpacking for ternary/SNN acceleration (backend path used by grok-ozempic#25)  
**Language**: Rust (+ CUDA `.cu` kernels)  
**Status**: v0 **extracted** (2026-08-14, issue [#21](https://github.com/rmems/operation-prometheus/issues/21)) — see [datasets/jsonl/myelin-accelerator-v0.jsonl](../../datasets/jsonl/myelin-accelerator-v0.jsonl)  
**Metadata card**: [datasets/cards/myelin-accelerator-v0.json](../../datasets/cards/myelin-accelerator-v0.json)

> Shortlist re-scored 2026-08-02 against measured pipeline yield (bot filter +
> `extract_review_signals` cap 8). Added `#26` and merged `#22`; dropped `#4`
> (0 kept signals) and `#2` (noise across mostly-`target/` files).

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#26](https://github.com/rmems/myelin-accelerator/pull/26) | packed ternary GEMV/GEMM kernels + CUDA 13.3.1 CI | gpu-compute | feature | Best overall (+2653/−111, 36 files). Advances GH #9 / LIM-890. |
| [#18](https://github.com/rmems/myelin-accelerator/pull/18) | License, CI, bitpacking, tests, benchmarks | gpu-compute | feature | Implements #16/#13/#12/#10/#11; 53 kept signals pre-cap. |
| [#22](https://github.com/rmems/myelin-accelerator/pull/22) | CLion CTest quality gate, nvtx, sm_120 PTX 9.2 | cuda | repair | Local-first CUDA gate for Blackwell; closes myelin#21. |
| [#7](https://github.com/rmems/myelin-accelerator/pull/7) | Corinth Canal CUDA/cust review→patch hardening | cuda | review-to-patch | 25 kept signals; review density on CUDA/cust integration. |
| [#6](https://github.com/rmems/myelin-accelerator/pull/6) | Feature-gated CUDA precursor to #7 | cuda | review-to-patch | 13 kept signals; precursor path for #7. |

## Measured review-signal yield

| PR | Kept after bot filter | Emitted | Unique bodies | Verdict |
|----|----------------------|---------|---------------|---------|
| #18 | 53 | 8 | 8 | shortlisted |
| #26 | 50 | 8 | 8 | **added** |
| #7 | 25 | 8 | 8 | shortlisted |
| #22 | 22 | 8 | 8 | **added** (merged) |
| #6 | 13 | 8 | 8 | shortlisted |
| #2 | 3 | — | — | **dropped** (target/ noise) |
| #4 | 0 | — | — | **dropped** |
