# Dataset Card: open-swe-traces trajectories v0

**Status:** extracted-v0 (external ingest, curated subsample)
**Created by:** Devin (Cognition) — `scripts/ingest_open_swe_traces.py`
**Schema:** [pr_trajectory.schema.json](../../schemas/pr_trajectory.schema.json) (v0)
**JSONL:** [open-swe-traces-v0.jsonl](../jsonl/open-swe-traces-v0.jsonl) (300 records)
**Machine card:** [open-swe-traces-v0.json](open-swe-traces-v0.json)
**Manifest:** [open-swe-traces-v0.manifest.json](../manifests/open-swe-traces-v0.manifest.json)
**Source doc:** [docs/source-repos/open-swe-traces.md](../../docs/source-repos/open-swe-traces.md)
**Issue:** GH #88 (epic GH #87, RM-2542)

## Source dataset

- **Dataset:** [nvidia/Open-SWE-Traces](https://huggingface.co/datasets/nvidia/Open-SWE-Traces) @ `4fa4c2ae9afc6b397bc50391d43450c79993c138`
- **License:** CC-BY-4.0 (dataset); per-record SPDX license preserved (`MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause` — all source rows pass the allowlist)
- **Config taken:** v1.0 — `openhands` + `sweagent` × `minimax_m25` + `qwen35_122b`, `swe-rebench-v2` subset only (63 parquet shards)
- **Teachers:** MiniMax-M2.5, Qwen3.5-122B-A10B — open-weight only
- **Join:** `nebius/SWE-rebench-V2` @ `d7608f017a29…` on `instance_id` supplies `pr_url`, `base_commit`, `created_at`, `problem_statement`; every candidate joined

## Filter funnel (pinned revision)

| Stage | Rows |
|-------|------|
| Census (all languages, all resolution states) | 151,219 |
| `resolved=1` | 48,293 |
| + language ∈ {python, rust} | 19,715 |
| + license allowlist | 19,715 (0 excluded) |
| + ≤3 trajectories per `instance_id` | 9,051 candidates (3,376 distinct instances) |
| + upstream join + non-empty `problem_statement` | 9,051 |
| + non-empty `model_patch` < 96 KiB | 9,007 (44 oversized dropped) |
| + strict-policy screen (home paths, secret-looking strings) | 8,020 records |
| Deterministic curated subsample (150/language, 1 per repo) | **300** |

Exclusion detail: 922 user-home-path hits, 74 secret-looking strings (a record
can hit both). Drops are recorded, never redacted — redaction would alter
evidence.

## Honesty notes

- `resolved=1` is NVIDIA's upstream FAIL_TO_PASS evaluation — **not** a merge
  event. `outcome: "merged"` describes the reference PR's state (SWE-bench
  instances are built from merged fix PRs); it does not claim the model patch
  was merged.
- `validation[].detail` names the upstream evaluation explicitly; `type:
  "test", result: "pass"` reflects resolved=1.
- `review_signals` absent on every record — trajectory distillates have no
  review evidence. The v0→v1 migration admits all 300 and marks
  `unavailable_fields: ["review_signals"]` per record.
- `quality_score` = 0.8 on all records (pipeline `score_quality` heuristic:
  merged + issue_context + passing validation; no review bonus possible).

## Contamination check (train/eval hygiene)

- SWE-bench Verified (500 rows) + SWE-bench Lite (323 rows) instance IDs:
  **zero overlap** with any candidate `instance_id`.
- Repo overlap: `pvlib/pvlib-python` only → forced `eval_only`.
- Split rule (repo-level, deterministic): `sha256(repo)[:8] % 5 == 0` → eval.

## Regeneration

`python scripts/ingest_open_swe_traces.py` re-runs against pinned revisions;
intermediates cache under `datasets/raw/open-swe-traces/` (gitignored). The
8,020-record filtered JSONL + sidecar + migration report live there too — only
the curated 300 are committed.
