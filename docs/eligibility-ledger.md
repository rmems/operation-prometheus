# Exhaustive eligibility and quality ledger

The v0.7 inventory accounts for every public pull request discovered under the
`rmems` user and `Limen-Neural` organization. It is an eligibility ledger, not
a released training split: terminal candidates remain quarantined until their
full engineering trajectory, policy result, and source license are supported
by evidence.

The workflow has a deliberate trust boundary:

1. `scripts/collect_source_inventory.py` queries GitHub read-only and writes one
   frozen source snapshot outside this repository.
2. `scripts/build_eligibility_ledger.py` performs all classification offline
   from that immutable snapshot and the versioned policy.
3. Only thin JSON/JSONL inventory records, duplicate reports, baseline evidence,
   and content hashes belong in `datasets/inventory/v0.7/`.

## Collect and build

Set an external data root and provide a GitHub token through the environment.
The collector refuses to choose an in-repository default path.

```bash
export PROMETHEUS_DATA_ROOT=/path/outside/operation-prometheus
export GITHUB_TOKEN=your-token-from-a-secret-store

python scripts/collect_source_inventory.py
python scripts/build_eligibility_ledger.py \
  --snapshot "$PROMETHEUS_DATA_ROOT/inventory/github-source-snapshot.json" \
  --check-determinism \
  --strict-baseline
```

After committing a generated inventory, CI or a reviewer can rebuild from the
same retained snapshot without changing files:

```bash
python scripts/build_eligibility_ledger.py \
  --snapshot "$PROMETHEUS_DATA_ROOT/inventory/github-source-snapshot.json" \
  --check \
  --check-determinism \
  --strict-baseline
```

The snapshot itself may contain public PR text needed for source hashing and
must not be committed. Do not put a token on the command line or in a policy,
manifest, shell transcript, or dataset card.

## Exhaustiveness and fail-closed behavior

Collection includes archived repositories and all PR states so closed-unmerged
work and the mutable open watchlist cannot disappear behind a merged-only
query. Private repositories returned to the authenticated caller are counted
as ignored but their identities and metadata are not stored in the snapshot.

The collector records a response hash and pagination position for every REST
and GraphQL page. It fails instead of emitting a partial snapshot when:

- a repository, PR, or formally linked issue lacks an immutable node ID;
- an immutable ID or repository/PR alias is duplicated;
- a cursor stalls, a connection total changes, or the final count disagrees;
- labels or closing-issue references exceed the collected connection page;
- a repository changes identity during collection.

The offline builder independently verifies the snapshot's canonical SHA-256,
page count, repository count, global PR count, and each repository's PR count.
It also rejects stale policy overrides, existing dataset rows absent from the
inventory in strict mode, and audit-baseline drift without recorded evidence.
Evidence-backed repository aliases in the policy map historical names and
transfers onto the current immutable repository ID; mutable owner/name text is
never allowed to orphan an otherwise conserved existing row.

The collection client accepts only named GraphQL `query` documents over HTTPS.
It has no mutation helper, and it rejects anonymous operations or any document
containing a mutation operation before opening a network connection.

## Ledger states

Every candidate has exactly one state and one or more reason codes:

- `included_positive` — a merged candidate explicitly approved with evidence;
- `included_negative` — a terminal negative, reverted, invalid, falsified, or
  superseded trajectory explicitly approved with evidence;
- `quarantined` — potentially useful terminal work whose full trajectory,
  artifact, policy, or licensing evidence is incomplete;
- `excluded` — deterministic dependency, release, documentation, or formatting
  exclusions, or an evidence-backed policy override;
- `watchlist_open` — open or draft work that remains mutable.

Automatic rules intentionally do not promote terminal PR metadata directly to
positive or negative training data. An override in `policy.json` must name the
immutable candidate ID and include non-empty `reason_codes` and
`evidence_refs`. A positive override is permitted only for a merged source PR,
and a watchlist override only for an open source PR.

## Quality record

The ledger records the following dimensions independently; there is no scalar
quality score:

- task or hypothesis clarity;
- before-state completeness;
- patch or action fidelity;
- chronology confidence;
- validation strength;
- outcome confidence;
- artifact reproducibility;
- license clarity;
- policy and privacy result.

Each dimension has an assessment, reason codes, and evidence references. PR
metadata alone normally produces `partial`, `missing`, or `unknown` evidence
for code, validation, artifact, and licensing dimensions. That is an explicit
signal to later trajectory collectors rather than a low score to average away.

## Outputs

`datasets/inventory/v0.7/` contains:

- `policy.json` — versioned owners, audit baseline, deterministic rules, and
  evidence-backed overrides;
- `repositories.jsonl` — one thin row per public repository;
- `candidates.jsonl` — one immutable-ID row per discovered PR;
- `duplicates.jsonl` — current-corpus exact duplicates, shared head OIDs, and
  within-repository near-title matches;
- `baseline-report.json` — expected versus observed counts and drift evidence;
- `manifest.json` — snapshot provenance, conservation counts, pagination
  hashes, state totals, and hashes of every generated output.

Revert and supersession references are extracted conservatively from PR text.
Qualified `owner/repository` URLs are resolved across the inventory; unqualified
references resolve only within the source repository. Candidates that formally
close the same immutable issue receive explicit multi-PR lineage edges.

The schemas are:

- `schemas/source_inventory.schema.json` for the frozen source snapshot;
- `schemas/eligibility_policy.schema.json` for policy and overrides;
- `schemas/eligibility_ledger.schema.json` for each candidate row.

The tracked inventory retains source licensing provenance but does not relicense
source-derived metadata under Operation Prometheus's Apache-2.0 license. A
candidate remains quarantined when source-license evidence is absent or only a
current repository-level license is known.
