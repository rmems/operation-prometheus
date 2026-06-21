# Datasets

This directory contains generated artifacts for Operation Prometheus trajectory datasets.

**Critical rules (see also root `.gitignore` and [AGENTS.md](../AGENTS.md)):**

- **Do not commit large raw datasets** or full GitHub issue/PR exports here.
- **Do not commit model weights** or other large binary artifacts.
- `datasets/raw/` is intended for local, temporary raw collection output from GitHub (gitignored).
- `datasets/jsonl/` is for cleaned, linked JSONL trajectory records — only commit small example files, schema samples, or cards.
- `datasets/cards/` holds lightweight metadata cards describing datasets (these are safe to commit).

Large data should live outside the repo (e.g. on object storage, Dolt, or a separate private datasets repo) and be referenced via manifests or cards.

This keeps the repository small, inspectable, and compliant with the project's prime directive and "Do Not" guidelines.

See:
- [AGENTS.md](../AGENTS.md) for overall rules
- [schemas/pr_trajectory.schema.json](../schemas/pr_trajectory.schema.json) for the canonical trajectory data shape (schema v0)
- [docs/source-repos.md](../docs/source-repos.md) for extraction shortlists and source repo tracking
