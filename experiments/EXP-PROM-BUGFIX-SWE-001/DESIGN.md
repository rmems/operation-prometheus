# EXP-PROM-BUGFIX-SWE-001

Dry-run-first teacher harness that seeds **synthetic bugfix SWE trajectories**
from Prometheus real PR records.

**Status:** scaffolding only. Audit before generate. No live OpenRouter calls
in CI. Do not commit generation outputs.

## Why

Raul wants alternate bugfix trajectories whose *root* comes from high-signal
merged Prometheus PRs, written by a single locked teacher:

`nvidia/nemotron-3-ultra-550b-a55b:free`

No fallback models in this EXP. Transport is a thin HTTPS client
([`providers/openrouter/`](../../providers/openrouter/README.md)), not the
official OpenRouter CLI.

## Frozen core seeds (n=8)

Filter on committed JSONL under `datasets/jsonl/*.jsonl`:

| Field | Required |
|---|---|
| `id` | one of the eight IDs in [`seed-manifest.json`](seed-manifest.json) |
| `task_type` | `bugfix` |
| `quality_score` | ≥ 0.90 |
| `outcome` | `merged` |

Secondary **holdout** (do not generate here): `training_use=repair` AND
`task_type ≠ bugfix`.

Gold `patch` is used **only** by the evaluator (`no_gold_leak`). It is never
copied into the teacher prompt.

## Prompt contract

Teacher input (see [`prompt-skeleton.md`](prompt-skeleton.md)):

- seed id, repo, language, domain
- `issue_context`
- truncated `before_context` (max 4000 chars)
- summarized review themes (not raw review dumps)
- validation kinds only (`ci`, `test`, …)

Ask for one alternate bugfix JSON matching
[`synth_bugfix_trajectory_v0.schema.json`](synth_bugfix_trajectory_v0.schema.json).

Three variant knobs (pilot = 8 × 3 = 24 calls when live):

1. `same-root-different-surface`
2. `narrower`
3. `broader+tests`

## Evaluator

Hard keep requires all of:

- `schema_ok`
- `task_type_bugfix`
- `patch_nonempty` (200–80000 chars)
- `no_gold_leak` (not equal to gold; line Jaccard < 0.85)
- `non_template` (fingerprint not a near-dup of a kept patch in this run)
- `provenance_complete`

Soft (recorded, do not flip keep → reject by themselves):

- `lang_match`
- `validation_present`

Yield ledger fields: `attempt_id`, `seed_id`, `variant`, `decision`
(`keep`|`reject`), `reject_codes`, `teacher_model`, `exp_id`, timestamps.
Stub: [`yield-ledger.stub.jsonl`](yield-ledger.stub.jsonl).

## CLI

```bash
python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001
```

| Flag | Default | Notes |
|---|---|---|
| `--exp` | required | only `EXP-PROM-BUGFIX-SWE-001` |
| `--model` | locked Ultra free | any other id is refused |
| `--variants-per-seed` | 3 | 1–3 |
| `--dry-run` | **true** | no network, no API key |
| `--live` | off | requires `OPENROUTER_API_KEY` |
| `--out-dir` | `experiments/EXP-PROM-BUGFIX-SWE-001/generations/` | gitignored |

`--live` and `--dry-run` together is an error.

## Out of scope

Hugging Face publish, `synthetic-factory/outputs/raw` writes, training,
self-merge, bulk new Prometheus extracts, committing generated trajectories.
