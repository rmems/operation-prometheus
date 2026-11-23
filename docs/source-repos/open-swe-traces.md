# nvidia/Open-SWE-Traces (external dataset)

<!-- index: [nvidia/Open-SWE-Traces](https://huggingface.co/datasets/nvidia/Open-SWE-Traces) | v0 extracted (external ingest) -->

**Source**: [nvidia/Open-SWE-Traces](https://huggingface.co/datasets/nvidia/Open-SWE-Traces) (Hugging Face dataset)
**Description**: Agentic SWE trajectories distilled from open-weight teachers (MiniMax-M2.5, Qwen3.5-122B-A10B, …) over SWE-bench-style tasks; resolved flag + model/reference patches per row
**Language**: Python + Rust slice extracted (9 languages in source)
**Status**: v0 **extracted** (2026-11-23), resolved-only Python+Rust, curated subsample — see [datasets/jsonl/open-swe-traces-v0.jsonl](../../datasets/jsonl/open-swe-traces-v0.jsonl)
**Issue**: [#88](https://github.com/rmems/operation-prometheus/issues/88) (epic [#87](https://github.com/rmems/operation-prometheus/issues/87))

This is the first **external** ingest: rows come from a published dataset, not
from GitHub collection. Provenance is pinned at the HF revision below; every
record's PR number, canonical pull URL, base commit OID, and timestamp come from
a verified join with the upstream instance source `nebius/SWE-rebench-V2`
(see the dataset card for the audit of that join).

## Provenance pins

| Item | Value |
|------|-------|
| Dataset | `nvidia/Open-SWE-Traces` |
| HF revision | `4fa4c2ae9afc6b397bc50391d43450c79993c138` (card v2.0 tree, 2026-10-28) |
| Config taken | `v1.0` — `openhands` + `sweagent` scaffolds × `minimax_m25` + `qwen35_122b` teachers, `swe-rebench-v2` subset only |
| Teachers (this config) | MiniMax-M2.5, Qwen3.5-122B-A10B — both open-weight; no hosted-frontier teacher |
| Dataset licence | CC-BY-4.0 (card tag `license:cc-by-4.0`) |
| Per-repo licences | every row carries SPDX id; allowlist filter MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause |
| Upstream join | `nebius/SWE-rebench-V2` @ `d7608f017a29ab256400ad4b73d5248d97204966`, on `instance_id` |

## What "resolved" means here

`resolved=1` is NVIDIA's upstream FAIL_TO_PASS evaluation result — the model
patch passed the instance's fail-to-pass tests inside the harness. It is **not**
a PR merge event: `outcome: "merged"` on v0 records describes the *reference*
PR's state (SWE-bench-family instances are built from merged fix PRs — the gold
patch is the PR diff), not the model patch. Validation detail strings name the
upstream evaluation explicitly so the claim stays auditable.

## Filter pipeline (GH #88)

resolved-only → language ∈ {python, rust} → SPDX allowlist → upstream join →
≤3 trajectories per `instance_id` → non-empty `model_patch` → patch < 96 KiB
(96 KiB is the strict-policy truncation-marker budget) → strict-policy
pre-screen (no user-home paths, no secret-looking tokens) → deterministic
repo-stratified curated subsample. Counts per stage live in the dataset card
and in `datasets/manifests/open-swe-traces-v0.manifest.json`.

## Regeneration

`scripts/ingest_open_swe_traces.py` reruns the whole pipeline against the
pinned revisions (intermediate caches land in `datasets/raw/open-swe-traces/`,
gitignored). The full filtered universe stays outside git by design; only the
curated v0 JSONL, card, and manifest are committed.
