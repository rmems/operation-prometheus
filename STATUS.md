# STATUS — Operation Prometheus

**By:** Grok Build Agent: Grok 4.5 (xAI)

<!-- BEGIN GENERATED: scripts/build_status.py -->

**Last updated:** 2026-08-20  
**Extracts:** 15 · **Trajectories:** 72  

<!-- Derived from datasets/manifests/*.manifest.json — do not edit by hand. -->

## Extracted datasets

| dataset | source repo | records | schema | extracted |
|---------|-------------|---------|--------|-----------|
| `corinth-canal-v0` | rmems/corinth-canal | 12 | pr_trajectory_v0 | 2026-08-16 |
| `grok-ozempic-v0` | rmems/grok-ozempic | 8 | pr_trajectory_v0 | 2026-08-16 |
| `limen-axon-encoder-v0` | Limen-Neural/axon-encoder | 3 | pr_trajectory_v0 | 2026-08-16 |
| `myelin-accelerator-v0` | rmems/myelin-accelerator | 5 | pr_trajectory_v0 | 2026-08-16 |
| `grok-ozempic-v1` | rmems/grok-ozempic | 5 | pr_trajectory_v0 | 2026-08-18 |
| `theseus-quarry-v0` | rmems/Theseus-Quarry | 5 | pr_trajectory_v0 | 2026-08-19 |
| `brainstem-daemon-v0` | Limen-Neural/brainstem-daemon | 4 | pr_trajectory_v0 | 2026-08-20 |
| `engram-parser-v0` | rmems/engram-parser | 1 | pr_trajectory_v0 | 2026-08-20 |
| `kinetic-signals-v0` | rmems/kinetic-signals | 5 | pr_trajectory_v0 | 2026-08-20 |
| `neuromod-v0` | Limen-Neural/neuromod | 5 | pr_trajectory_v0 | 2026-08-20 |
| `spike-viz-v0` | rmems/spike-viz | 3 | pr_trajectory_v0 | 2026-08-20 |
| `spikestream-jl-v0` | rmems/SpikeStream.jl | 4 | pr_trajectory_v0 | 2026-08-20 |
| `thalamic-relay-v0` | rmems/thalamic-relay | 3 | pr_trajectory_v0 | 2026-08-20 |
| `worktrees-hives-v0` | rmems/worktrees-hives | 5 | pr_trajectory_v0 | 2026-08-20 |
| `xai-dissect-v0` | rmems/xai-dissect | 4 | pr_trajectory_v0 | 2026-08-20 |

## Trajectory quality

### corinth-canal-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #142 | ml-infra | review-to-patch | bugfix | 0.90 | 8 | 3 |
| #138 | gpu-compute | repair | refactor | 0.90 | 2 | 3 |
| #128 | ml-infra | review-to-patch | refactor | 0.90 | 6 | 4 |
| #127 | tools | review-to-patch | refactor | 0.90 | 8 | 4 |
| #126 | gpu-compute | review-to-patch | refactor | 0.95 | 7 | 4 |
| #125 | ml-infra | review-to-patch | refactor | 0.90 | 8 | 4 |
| #96 | tools | validation | feature | 0.78 | 8 | 3 |
| #95 | ml-infra | feature | feature | 0.58 | 8 | 3 |
| #94 | ml-infra | repair | feature | 0.94 | 8 | 3 |
| #91 | ml-infra | feature | feature | 0.62 | 8 | 3 |
| #89 | gpu-compute | validation | test | 0.92 | 8 | 3 |
| #82 | gpu-compute | repair | feature | 0.86 | 8 | 3 |

### grok-ozempic-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #43 | ml-infra | review-to-patch | feature | 0.95 | 8 | 4 |
| #42 | ml-infra | review-to-patch | feature | 0.90 | 8 | 4 |
| #33 | testing | review-to-patch | refactor | 0.90 | 8 | 3 |
| #29 | validation | validation | test | 0.90 | 8 | 4 |
| #26 | validation | validation | feature | 0.95 | 8 | 3 |
| #25 | ml-infra | feature | feature | 0.95 | 8 | 2 |
| #24 | validation | validation | feature | 0.95 | 8 | 3 |
| #11 | ml-infra | feature | feature | 0.95 | 8 | 3 |

### limen-axon-encoder-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #50 | security | repair | security | 0.95 | 8 | 4 |
| #41 | api | review-to-patch | bugfix | 0.95 | 8 | 3 |
| #37 | snn | review-to-patch | feature | 0.95 | 8 | 4 |

### myelin-accelerator-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #26 | gpu-compute | feature | feature | 0.90 | 8 | 4 |
| #22 | cuda | repair | bugfix | 0.90 | 8 | 4 |
| #18 | gpu-compute | feature | feature | 0.90 | 8 | 3 |
| #7 | cuda | review-to-patch | feature | 0.95 | 8 | 2 |
| #6 | cuda | review-to-patch | feature | 0.95 | 8 | 2 |

### grok-ozempic-v1

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #74 | quantization | review-to-patch | feature | 0.95 | 8 | 3 |
| #72 | quantization | review-to-patch | feature | 0.90 | 8 | 3 |
| #71 | quantization | feature | feature | 0.90 | 8 | 4 |
| #69 | quantization | feature | feature | 0.90 | 8 | 4 |
| #42 | ml-infra | review-to-patch | feature | 0.90 | 8 | 4 |

### theseus-quarry-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #13 | telemetry | feature | feature | 0.95 | 8 | 4 |
| #12 | telemetry | repair | bugfix | 0.90 | 8 | 3 |
| #11 | telemetry | feature | feature | 0.90 | 2 | 3 |
| #9 | gpu-compute | feature | feature | 0.90 | 7 | 3 |
| #8 | infra | repair | refactor | 0.95 | 8 | 3 |

### brainstem-daemon-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #25 | snn | repair | bugfix | 0.95 | 6 | 4 |
| #24 | api | review-to-patch | refactor | 0.95 | 7 | 4 |
| #8 | infra | feature | refactor | 0.95 | 8 | 3 |
| #3 | snn | feature | feature | 0.85 | 2 | 2 |

### engram-parser-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #44 | ml-infra | feature | feature | 0.90 | 8 | 4 |

### kinetic-signals-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #39 | telemetry | validation | test | 0.95 | 8 | 4 |
| #35 | telemetry | validation | test | 0.95 | 6 | 4 |
| #17 | snn | repair | refactor | 0.95 | 3 | 3 |
| #6 | infra | feature | refactor | 0.95 | 3 | 4 |
| #1 | ml-infra | bug-prediction | refactor | 0.75 | 1 | 1 |

### neuromod-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #15 | ml-infra | review-to-patch | refactor | 0.95 | 4 | 3 |
| #9 | api | bug-prediction | refactor | 0.85 | 2 | 2 |
| #8 | snn | bug-prediction | refactor | 0.75 | 2 | 1 |
| #5 | snn | feature | feature | 0.95 | 4 | 1 |
| #2 | snn | review-to-patch | refactor | 0.85 | 7 | 1 |

### spike-viz-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #24 | visualization | feature | feature | 0.95 | 2 | 3 |
| #23 | io | review-to-patch | bugfix | 0.95 | 7 | 2 |
| #22 | io | feature | feature | 0.90 | 5 | 4 |

### spikestream-jl-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #25 | snn | validation | test | 0.80 | 0 | 4 |
| #22 | api | repair | refactor | 0.85 | 0 | 3 |
| #21 | tools | validation | test | 0.95 | 2 | 3 |
| #7 | snn | feature | feature | 0.95 | 8 | 2 |

### thalamic-relay-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #23 | gpu-compute | repair | bugfix | 0.95 | 5 | 4 |
| #22 | systems | validation | test | 0.90 | 1 | 3 |
| #20 | gpu-compute | feature | feature | 0.95 | 4 | 4 |

### worktrees-hives-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #79 | tools | review-to-patch | bugfix | 0.90 | 2 | 4 |
| #78 | tools | review-to-patch | feature | 0.95 | 8 | 4 |
| #65 | ml-infra | feature | feature | 0.90 | 8 | 2 |
| #63 | agentic-workflow | feature | feature | 0.95 | 8 | 2 |
| #61 | agentic-workflow | feature | feature | 0.90 | 8 | 3 |

### xai-dissect-v0

| PR | domain | training_use | task_type | quality | signals | validation |
|----|--------|--------------|-----------|---------|---------|------------|
| #36 | quantization | feature | feature | 0.95 | 6 | 3 |
| #34 | export | feature | feature | 0.90 | 7 | 3 |
| #32 | export | feature | feature | 0.95 | 8 | 3 |
| #24 | ml-infra | feature | feature | 0.95 | 7 | 3 |

<!-- END GENERATED -->

## Accomplished this sprint

1. **Read-only GitHub collector** (`scripts/collect_pr_records.py` + `scripts/lib/`) — merged PR #12  
2. **Normalizer** → schema-valid JSONL with quality scores, bot filter, secret redaction  
3. **corinth-canal-v0** — 6 trajectories extracted and merged  
4. **Limen-Neural Wave A pilot** — shortlist docs + **limen-axon-encoder-v0** (3 PRs)  
5. **grok-ozempic-v0** — **8** trajectories (incl. Python **#42** via #20 / PR #35)  
6. **#18/#19** — review_signals dedupe + `language_by_pr` (merged #34); **resolved**  
7. **#14** — `PROMETHEUS_DATA_ROOT` sibling layout (merged #22); package **0.4.0** tagged  
8. **v0.5 epic #31** closed; **myelin-accelerator-v0** extracted (#21) — 5 trajectories  
9. **#20** — grok-ozempic **#42** Python trajectory on v0 (merged #35); **resolved**  
10. **grok-ozempic-v1** — 5 trajectories (GOZ1 v2/v3 + expert-remedy wave `#69`/`#71`/`#72`/`#74` + Python `#42`)  

## Remaining gaps

- Later Limen waves (neuromod, SpikeStream, kinetic-signals, limbic-critic) not extracted  
- Large patches still truncated; bot review noise high on Limen PRs  
- Manual human re-inspection sample still recommended before training runs  

## Next-sprint roadmap (prioritized)

1. **v0.6 fleet** — grok-ozempic-v1 extracted; remaining shortlist refreshes (#24/#25), waves B/C  
2. **SFT / preference pairs** — v0.7 (#23)  

## Verification checklist

```bash
ruff check scripts/
pytest -q
python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl
```
