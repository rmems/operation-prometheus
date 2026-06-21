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

This directory is populated with this README. Provider-specific subdirectories (e.g. `xai/`, `openai/`, `anthropic/`, `local/`) will be added as extraction agents and eval harnesses are built.

Keep this directory small and focused on integration, not assets.
