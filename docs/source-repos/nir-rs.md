# nir-rs

<!-- index: [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs) | v0 extracted -->

**Repo**: [Limen-Neural/nir-rs](https://github.com/Limen-Neural/nir-rs)  
**Description**: Rust NIR interchange (graph IR, HDF5 `.nir`, untrusted-read hardening, serde)  
**Language**: Rust  
**Status**: v0 **extracted** (2026-09-04, issue [#66](https://github.com/rmems/operation-prometheus/issues/66), Wave D) — see [datasets/jsonl/nir-rs-v0.jsonl](../../datasets/jsonl/nir-rs-v0.jsonl)  
**Metadata card**: [datasets/cards/nir-rs-v0.json](../../datasets/cards/nir-rs-v0.json)

## Shortlisted PRs

| PR | Title | Domain | Bucket | Signal |
|----|-------|--------|--------|--------|
| [#20](https://github.com/Limen-Neural/nir-rs/pull/20) | feat(io): v0.3 — HDF5 `.nir` read/write | io | feature | 123 kept / 8 emitted. Closes #9 / #10 / #11. |
| [#23](https://github.com/Limen-Neural/nir-rs/pull/23) | fix(io): harden untrusted reads and atomic writes | io | repair | 46 kept. Closes #21 / #22. task_type security. |
| [#18](https://github.com/Limen-Neural/nir-rs/pull/18) | feat: v0.2 Core IR | io | feature | 17 kept. Closes #12 / #7 / #8. |
| [#24](https://github.com/Limen-Neural/nir-rs/pull/24) | feat(graph): add feature-gated serde support | api | feature | 4 kept. Closes #13. |

## Measured review-signal yield

| PR | Kept | Emitted | Unique | Verdict |
|----|------|---------|--------|---------|
| #20 | 123 | 8 | 8 | shortlisted |
| #23 | 46 | 8 | 8 | shortlisted |
| #18 | 17 | 8 | 8 | shortlisted |
| #24 | 4 | 4 | 4 | shortlisted |
| #35 | 0 | 0 | 0 | dropped (0 yield) |
| #36 | 0 | 0 | 0 | dropped (0 yield) |
| #38 | — | — | — | skipped (Docker dual-publish) |

## Considered and rejected

- **`#38`** — Docker dual-publish to GHCR/Docker Hub.
- **`#35`, `#36`** — test corpus / fuzz, 0 kept signals.
- Release notes, CHANGELOG, docs examples, CI matrix — skip list.
