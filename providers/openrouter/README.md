# OpenRouter adapter

Thin **stdlib `urllib`** client for the OpenAI-compatible endpoint:

`https://openrouter.ai/api/v1/chat/completions`

This is **not** the official OpenRouter CLI. No extra Python dependency.

## Experiment lock (EXP-PROM-BUGFIX-SWE-001)

Teacher model is **hard-locked**:

`nvidia/nemotron-3-ultra-550b-a55b:free`

There is **no fallback model**. Any other `--model` id is rejected before a
request is built.

## Dry-run first

The generator defaults to `--dry-run`:

- writes redacted planned request payloads
- feeds fixture / synth responses through the evaluator
- exits 0 with **no network** and **no** `OPENROUTER_API_KEY`

`--live` is opt-in and requires `OPENROUTER_API_KEY` in the environment.
CI and this repository must not make live calls.

## Environment

| Variable | Required | When |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | `--live` only |
| `OPENROUTER_API_KEY` | no | default `--dry-run` |

Never commit `.env`, tokens, or generation outputs. See the root
[`.gitignore`](../../.gitignore).

## Entry point

```bash
python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001
# equivalent: --dry-run is the default

# opt-in live (refuses unless the locked Ultra free model is selected)
# export OPENROUTER_API_KEY=...
# python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001 --live
```

See [experiments/EXP-PROM-BUGFIX-SWE-001/DESIGN.md](../../experiments/EXP-PROM-BUGFIX-SWE-001/DESIGN.md).
