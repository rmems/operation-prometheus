# rmems wave C (Wave C pilot extracted)

<!-- index: [rmems (org)](https://github.com/rmems) | Wave C pilot extracted -->

**Org**: [rmems](https://github.com/rmems) — wave C source repos from issue
[#29](https://github.com/rmems/operation-prometheus/issues/29).  
**Status**: **Wave C pilot extracted** (2026-08-20) — four dataset cards
(`thalamic-relay-v0`, `xai-dissect-v0`, `spike-viz-v0`, `engram-parser-v0`).
Per-repo shortlists live in `docs/source-repos/<repo>.md`.

> Review counts below that are not restated from the per-repo docs are **raw**
> GitHub API totals from the 2026-08-16 pointer scan. Extraction used live
> `list_merged_prs.py` + `is_bot_user` / `extract_review_signals` yield.

## Extracted this PR

| Repo | Card | PRs | Why this wave |
|------|------|-----|----------------|
| [thalamic-relay](thalamic-relay.md) | `thalamic-relay-v0` | #20, #23, #22 | GPU-safety cluster; strongest Wave C cluster after xai-dissect. |
| [xai-dissect](xai-dissect.md) | `xai-dissect-v0` | #32, #34, #24, #36 | Export-contract domain PRs. **#48 bulk CI excluded.** |
| [spike-viz](spike-viz.md) | `spike-viz-v0` | #24, #23, #22 | Tiny repo; #22→#23 review-to-patch pair plus raster renderer. |
| [engram-parser](engram-parser.md) | `engram-parser-v0` | #44 | GGUF v3 + IQ layouts. Dependabot-heavy; only one real-code PR survived yield/noise filters. |

## Deferred (capacity)

Pilot cap is **up to 4 cards**. These repos stay pointers-only until a later
wave; they were not collected:

| Repo | Candidate PRs | Why deferred |
|------|---------------|--------------|
| [agoge-forger](https://github.com/rmems/agoge-forger) | #74, #73, #71, #67 | Fine-tuning forge; moderate review density. Below GPU-safety / export-contract priority. |
| [LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl) | #45, #33 | Julia; #45 is a single 100-review outlier. New language for a later card. |
| [silicon-hdl](https://github.com/rmems/silicon-hdl) | #52, #51 only | First HDL language; INIT_FILE E1/E2 pair worth a dedicated extract, not this 4-card pilot. |
| [hybrid-fusion](https://github.com/rmems/hybrid-fusion) | #17, #1 optional | Older test/feature PRs; newer API-contract wave is thin (≤6 rev). |

## Pointer scan (2026-08-16, still useful)

Several repos were transferred **Limen-Neural → rmems** in 2026-08
("post-transfer hygiene" PRs were dropped at extraction).

| Repo | Note |
|------|------|
| [xai-dissect](https://github.com/rmems/xai-dissect) | #48 is a CI-modernization monster — screened against bulk-CI exclusion; #32 export contract is the domain anchor for grok-ozempic. |
| [engram-parser](https://github.com/rmems/engram-parser) | Real code wave is #44 plus the early ladder; corinth-canal#156 retargets its safetensors-inspect half here. |
| [thalamic-relay](https://github.com/rmems/thalamic-relay) | GPU-safety supervisor wave #20–#23 is uniformly dense. |
| [spike-viz](https://github.com/rmems/spike-viz) | Only 4 merged PRs; #23 exists to answer #22's review. |
