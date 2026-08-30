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

Preferred local layout for scale: set **`PROMETHEUS_DATA_ROOT`** (e.g. `~/rmems/prometheus-data`) so the collector writes `raw/<owner_repo>/pr-N.json` outside the git tree. See [datasets/README.md](../datasets/README.md).

The exhaustive eligibility ledger uses a separate frozen source snapshot under
`$PROMETHEUS_DATA_ROOT/inventory/`. That snapshot stays outside Git. The
tracked ledger stores only selected public metadata, immutable identifiers,
reasoned classifications, and hashes. Private repositories visible to the
collector are ignored without retaining their names or metadata. See
[eligibility-ledger.md](eligibility-ledger.md) for the pagination,
conservation, and read-only guarantees.

## Manual Inspection Requirement

Before any generated dataset is published or used for training:

- A human (or explicit recorded review step) must inspect a sample of the records.
- Confirm that no excluded material is present.
- Confirm that the trajectory still carries useful engineering signal (issue → review → patch → validation → outcome).

## Public Engineering History vs. Chat Log Scraping

This project focuses on the **engineering trajectory** visible in public code review and version control:

```text
issue/review signal → before state → patch/fix → validation → outcome
```

It is **not** a general web scrape of LLM chat logs. Public PR discussion, code review, and commit history are distinct from proprietary model outputs or private conversation transcripts.

See also:
- [AGENTS.md](../AGENTS.md) — "Do Not" section and prime directive
- Root `.gitignore` — rules for raw data and model weights
- [datasets/README.md](../datasets/README.md) — guidance on what may be committed

## Questions or Concerns

Open an issue or discussion in this repository. All policy updates should be tracked as changes to this document and referenced from the root README.

## Licensing Model

Operation Prometheus's own tooling, schemas, validators, tests, and
documentation are licensed under **Apache-2.0** (see root [LICENSE](../LICENSE)).

This repository-level license does **not** relicense incorporated
source-derived material. Every trajectory extracted from a public source
repository retains that repository's own license:

- The trajectory schema (`schemas/trajectory_v1.schema.json`,
  `schemas/pr_trajectory.schema.json`) carries a machine-readable `license`
  field per record, so source-license provenance travels with the data.
- Per-source-repository license documentation is required to live in
  [docs/source-repos/](source-repos/) and to be summarized in each dataset
  card's "License / provenance" section. Existing v0 source docs and cards
  are being backfilled with explicit source-license identities; this
  requirement applies going forward regardless of backfill status.
- The canonical Hugging Face dataset card must document the full set of
  represented source licenses rather than implying a single blanket license
  for the dataset.

See [NOTICE](../NOTICE) for the complete distinction between
Operation Prometheus-owned material and incorporated source-derived material.

## Anti-Hallucination and Evidence Policy

Trajectory generation must rely strictly on verifiable source evidence. We must never invent:
- Hidden chain-of-thought or internal reasoning that was not published.
- Reviewer intent that cannot be evidenced.
- Undisclosed agent or model identities (e.g. attributing human actions to models, or vice versa, without proof).
- Execution success, test results, or causal explanations not present in the evidence.

If evidence is unavailable, explicitly encode it as such or mark it null, rather than filling fields with inferences or fabricated details.
