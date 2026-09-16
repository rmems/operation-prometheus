# Event collector and content-addressed snapshots

Operation Prometheus collects public GitHub engineering history read-only.
This document covers the inventory-driven, resumable collector added for the
v0.7 exhaustive corpus (GitHub #50 / RM-735).

The collector **never writes to source GitHub repositories**.  All GitHub
access goes through the existing GET-only client.

## Per-PR mode (unchanged)

```bash
python scripts/collect_pr_records.py \
  --repo rmems/corinth-canal \
  --pr 82,89,91
```

`--repo` / `--pr` still write `pr-N.json` under `--out-dir` or
`$PROMETHEUS_DATA_ROOT/raw/<owner_repo>/`.  `--skip-existing` still skips
shards that already exist.

## Inventory-driven batches

Drive collection from the v0.7 eligibility ledger (both `rmems` and
`Limen-Neural`) or a simple `{repo, pr}` JSONL:

```bash
export PROMETHEUS_DATA_ROOT=/path/outside/operation-prometheus
export GITHUB_TOKEN=your-token-from-a-secret-store

python scripts/collect_pr_records.py \
  --inventory datasets/inventory/v0.7 \
  --states quarantined,included_positive,included_negative,watchlist_open \
  --snapshots \
  --continue-on-error
```

`--inventory` accepts a `candidates.jsonl` file or a ledger directory.  Work
items are sorted by `(repo, pr_number, item_id)` so the same frozen inventory
always produces the same collection order.

## Resume

Interruptions and GitHub rate limits do not emit duplicate events.  Each PR
is one shard: the raw JSON is written atomically, then the resume document
records that item as `complete` together with the shard's SHA-256.  A crash
mid-PR leaves the item `in_progress` / `failed` so the next run retries it.

Resume state defaults to `$PROMETHEUS_DATA_ROOT/collector-state.json`.  A
completed shard whose on-disk hash no longer matches is re-collected rather
than trusted by filename.

## Snapshots

`--snapshots` (default on for inventory, off for `--repo/--pr`) fetches git
commit objects and before/after blobs through the GitHub Git Data API and
stores them in a content-addressed store:

```text
$PROMETHEUS_DATA_ROOT/artifacts/objects/<hh>/<sha256>
```

Cached objects are re-hashed on read.  Filename match alone is never enough.
Deleted or inaccessible commits are written into `pr-N.pack.json` with
`availability: missing` and the resume item is marked `quarantined`.  The pack
is never silently marked `complete`.

## v1 trajectories

```bash
python scripts/build_trajectory_jsonl.py \
  --raw-dir "$PROMETHEUS_DATA_ROOT/raw/rmems_corinth-canal" \
  --card datasets/cards/corinth-canal-v0.json \
  --schema-version v1 \
  --out /tmp/corinth-canal-v1.jsonl
```

`--schema-version v0` remains the default.  v1 rows are typed event-sourced
trajectories: chronological events with `code_state`, artifacts addressed by
SHA-256, and explicit missing evidence.  Validate with
`scripts/validate_jsonl.py --strict-policy`.
