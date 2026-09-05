# Teacher prompt skeleton (EXP-PROM-BUGFIX-SWE-001)

The generator builds two chat messages. The gold seed `patch` must never appear
in either message.

## System

You are writing an *alternate* bugfix trajectory for Operation Prometheus
experiment `EXP-PROM-BUGFIX-SWE-001`. Return a single JSON object that matches
`synth_bugfix_trajectory_v0`. Do not copy a hidden gold patch. `task_type` must
be `bugfix`. `training_use` must be `repair`. `outcome` must be `merged`.
`provenance.kind` must be `synthetic` and must link `seed_id`.

## User

Fields provided (and only these):

- `seed_id`, `repo`, `language`, `domain`
- `issue_context`
- `before_context` (truncated to ≤4000 characters)
- `review_themes` (short summaries; not raw review threads)
- `validation_kinds` (e.g. `ci`, `test`)
- `variant` knob, one of:
  - `same-root-different-surface` — same root cause, different fix surface
  - `narrower` — smaller, more conservative fix
  - `broader+tests` — broader fix that includes tests

Do **not** include a `gold_patch` / `patch` from the seed.

## Expected JSON keys

`id`, `seed_id`, `exp_id`, `teacher_model`, `generated_at`, `language`,
`domain`, `task_type`, `training_use`, `issue_context`, `before_context`,
`patch`, `validation`, `outcome`, `provenance`.
