# Beads for Operation Prometheus

This project uses the **global personal Beads database** (prefix: `raulmc-`) located at:

- `~/.beads/` (embedded Dolt + issues.jsonl)

## Making `bd` usable in this directory (global DB)

By default, `bd` commands look for a local `.beads/` workspace in the current directory tree.

To use the global DB from this repo:

```bash
# One-off
BEADS_DIR=/home/raulmc/.beads bd list --status=open

# Recommended: alias or direnv for this shell session / project
export BEADS_DIR=/home/raulmc/.beads
bd ready
bd prime
```

Or add a shell alias (in ~/.bashrc or similar):

```bash
alias bd='BEADS_DIR=/home/raulmc/.beads bd'
```

Then plain `bd ...` will work when you are in this (or any) project that shares the personal global tracker.

## Current project issues

All Operation Prometheus work items are tracked under the `raulmc-` prefix in the shared DB.

Relevant GitHub issues are mirrored here:

- GitHub #1 (scaffold) → completed on this branch
- GitHub #2 (schema v0) → raulmc-vge (in progress)
- GitHub #3 (data policy) → raulmc-9cq (in progress)

See `bd show <id>` for details, acceptance criteria, and links back to https://github.com/rmems/operation-prometheus/issues/N

## Workflow (per AGENTS.md + bd prime)

- Always use `bd` (with correct BEADS_DIR) for task tracking. Never markdown TODOs.
- `bd ready` to find available work
- `bd update <id> --claim` to start
- `bd close <id>` when done
- At end of session:
  1. git status
  2. git add <changed files>
  3. BEADS_DIR=/home/raulmc/.beads bd dolt pull
  4. git commit -m "..."
  5. (optional) BEADS_DIR=/home/raulmc/.beads bd dolt push   # will be no-op if no remote configured

## Notes

- The global DB is the single source of truth for the user's cross-project tasks.
- This repo does **not** maintain its own .beads/embeddeddolt (that would fragment tracking).
- `.beads/` in this repo only contains this README (other contents are gitignored per .gitignore).

See root AGENTS.md for full Operation Prometheus rules and validation commands.
