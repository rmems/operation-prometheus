# rmems wave C (pointers only)

<!-- index: [rmems (org)](https://github.com/rmems) | pointers only -->

**Org**: [rmems](https://github.com/rmems) — wave C source repos from issue
[#29](https://github.com/rmems/operation-prometheus/issues/29).  
**Status**: **pointers only** (2026-08-16 live scan) — no shortlists, no extraction.
Full per-repo shortlists land when [#29](https://github.com/rmems/operation-prometheus/issues/29)
is decomposed; a wave C repo then graduates to its own `docs/source-repos/<repo>.md`.

> Review counts are **raw** GitHub API `reviews` totals (pre bot-filter), from the
> most recent 8 merged PRs per repo — older history is unscanned. Several repos were
> transferred **Limen-Neural → rmems** in 2026-08 ("post-transfer hygiene" PRs);
> all links below already point at rmems.

| Repo | Candidate PRs | Note |
|------|---------------|------|
| [xai-dissect](https://github.com/rmems/xai-dissect) | #48 (**137 rev / 200 threads**), #37 (50 rev), #50 (37 rev), #32 (23 rev) | Rust. #48 is a CI-modernization monster — screen against the [bulk-CI exclusion](_index.md#avoid-for-v0-training) despite the density; #32 export contract is the domain anchor for grok-ozempic. |
| [engram-parser](https://github.com/rmems/engram-parser) | #44 (GGUF v3 parser + IQ wire layouts), #57 (reverses #10; 8 threads), #23, #21, #1 | Rust. Recent history is Dependabot-dominated (20+ of 35 merged); the real code wave is #44 and the early #17–#23 ladder. corinth-canal#156 retargets its safetensors-inspect half here. |
| [agoge-forger](https://github.com/rmems/agoge-forger) | #85 (11 rev), #73 (9 rev), #74, #86, #84 | Python (+ Rust tools). Fine-tuning forge; steady issue-linked repair wave (#64–#68 issues), moderate review density. |
| [spike-viz](https://github.com/rmems/spike-viz) | #22 → #23 (16 rev) review-to-patch pair, #24 (13 rev / 15 threads) | Python. Only 4 merged PRs; #23 exists to answer #22's review — extract as a pair. |
| [thalamic-relay](https://github.com/rmems/thalamic-relay) | #23 (55 rev), #22 (51 rev), #20 (49 rev / 36 threads), #21 (23 rev) | Rust. GPU-safety supervisor wave #20–#23 is uniformly dense — strongest wave C cluster after xai-dissect. |
| [LiquidCortex.jl](https://github.com/rmems/LiquidCortex.jl) | #45 (**100 rev / 52 threads**), #32 (19 rev), #31 (10 rev) | Julia. #45 (experimental step plasticity + GPU step options) is a single outlier carrying most of the repo's signal. |
| [silicon-hdl](https://github.com/rmems/silicon-hdl) | #51 (43 rev), #77 (16 rev), #52 (12 rev), #78 (8 rev / 17 threads) | SystemVerilog — would be the dataset's first HDL language; #51/#52 INIT_FILE E1/E2 pair, #78 gated LIF/STDP merged 2026-08-16. |
| [hybrid-fusion](https://github.com/rmems/hybrid-fusion) | #19 (27 rev), #17 (17 rev), #16 (14 rev), #30–#32 API-contract wave | Rust. Older test/feature PRs out-measure the newer contract wave (#30–#32, ≤6 rev each). |
