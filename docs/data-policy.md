# Data Policy and Dataset Hygiene

**Status**: Draft (implements GitHub issue #3)

Operation Prometheus converts **public** GitHub engineering history into structured training datasets.

We are committed to responsible use of public artifacts and keeping the repository small, inspectable, and free of sensitive material.

## Allowed Public Sources

We may extract and normalize from public repositories:

- PR metadata (titles, bodies, labels, milestones, state transitions)
- Issue and PR comments (public discussion)
- Review comments and suggestions
- Diffs and commits (code changes)
- CI / check run summaries (public workflow results)
- Safe experiment artifacts that were intentionally made public (e.g. benchmark outputs, public logs)

All of the above must come from repositories that are publicly accessible without authentication.

## Excluded Sources

We **must not** commit or use as primary training data:

- Private credentials, tokens, API keys, or secrets of any kind
- Private local configuration files (e.g. `.env`, personal machine settings)
- Raw closed-model chat logs as the primary training corpus (per AGENTS.md "Do Not")
- Large model weights or artifacts committed directly to this Git repository (see AGENTS.md and `.gitignore`)
- Private or internal-only discussions, even if accidentally exposed

Raw GitHub API exports (issues.jsonl, prs.jsonl, etc.) are treated as **temporary working artifacts** until they have been:
1. Normalized into trajectory records
2. Manually inspected for policy compliance
3. Reduced to the minimal public signal needed

Large raw exports should live outside the repo (local disk, object storage, or a private datasets mirror) and are gitignored by default.

## Manual Inspection Requirement

Before any generated dataset is published or used for training:

- A human (or explicit recorded review step) must inspect a sample of the records.
- Confirm that no excluded material is present.
- Confirm that the trajectory still carries useful engineering signal (issue → review → patch → validation → outcome).

## Public Engineering History vs. Chat Log Scraping

This project focuses on the **engineering trajectory** visible in public code review and version control:

```
issue/review signal → before state → patch/fix → validation → outcome
```

It is **not** a general web scrape of LLM chat logs. Public PR discussion, code review, and commit history are distinct from proprietary model outputs or private conversation transcripts.

See also:
- [AGENTS.md](../AGENTS.md) — "Do Not" section and prime directive
- Root `.gitignore` — rules for raw data and model weights
- [datasets/README.md](../datasets/README.md) — guidance on what may be committed

## Questions or Concerns

Open an issue or discussion in this repository. All policy updates should be tracked as changes to this document and referenced from the root README.
