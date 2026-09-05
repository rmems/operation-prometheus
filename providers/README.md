# Providers

Configuration, thin clients, and adapters for **external model / inference providers**.

This project uses external providers (e.g. xAI, OpenAI-compatible, Anthropic, local Ollama/vLLM) instead of checking model weights into the repository.

## What belongs here
- Provider client wrappers or config schemas (for evals, future extraction agents, etc.)
- Example environment variable names and endpoint configuration
- Thin adapter code (no weights, no large artifacts)

## What does NOT belong here
- API keys, tokens, or credentials (use environment variables or secret stores)
- Model weights, checkpoints, GGUF files, safetensors, etc.
- Large downloaded model artifacts

See:
- [AGENTS.md](../AGENTS.md) (Do Not section)
- [docs/data-policy.md](../docs/data-policy.md)
- Root [.gitignore](../.gitignore)

## Current status

- [`openrouter/`](openrouter/README.md) — thin stdlib HTTPS client for
  `https://openrouter.ai/api/v1/chat/completions`, used by
  `scripts/generate_bugfix_synth.py` for **EXP-PROM-BUGFIX-SWE-001**.
  Dry-run is the default (no network, no API key). The teacher is locked to
  `nvidia/nemotron-3-ultra-550b-a55b:free` with no fallback models.

Other provider-specific subdirectories (e.g. `xai/`, `openai/`, `anthropic/`,
`local/`) can be added as extraction agents and eval harnesses are built.

Keep this directory small and focused on integration, not assets.
