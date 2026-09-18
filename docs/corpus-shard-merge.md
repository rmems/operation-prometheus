# Canonical global corpus merge

The v0.7 corpus is extracted as three non-overlapping shards (#56, #57, #58).
This merge step consumes those shard outputs and the frozen eligibility
inventory. It does not recollect GitHub, relabel records, delete near-duplicates,
or publish to Hugging Face.

## Assignment

A repository belongs to exactly one shard:

```text
int(sha256(github_repository_node_id)[0:8], 16) % 3
```

`github_repository_node_id` is the immutable GraphQL repository ID stored as
`repository_id` on inventory rows (for example `R_kgDOR-W7cg`). The first eight
characters of the UTF-8 SHA-256 hex digest are interpreted as a base-16 integer.

## Shard contract

Each shard directory `shard-{n}/` contains:

- `manifest.json` — shard number, assignment rule, inventory revision, schema
  versions, sorted repository IDs, conserved counts, record file digest, and a
  self-digest (`manifest_sha256`);
- `records.jsonl` — one thin envelope per assigned inventory row. The envelope
  is either a materialized trajectory reference or an explicit
  quarantine/exclusion/watchlist outcome with reason codes.

The merger copies record line bytes as-is. It does not canonicalize or relabel
shard-owned JSON.

## Merge

```bash
python scripts/merge_corpus_shards.py \
  --inventory-dir datasets/inventory/v0.7 \
  --shards-dir datasets/shards/v0.7 \
  --out-dir datasets/corpus/v0.7 \
  --check-determinism
```

`--check` compares the committed global artifacts instead of rewriting them.

The command fails closed on a missing shard, a duplicate repository or record,
a foreign-shard member (wrong modulus), a digest mismatch, a schema mismatch,
or an inventory row that no shard accounted for.

Outputs:

- `records.jsonl` — shard records ordered by `candidate_id`, original bytes preserved;
- `manifest.json` — canonical global manifest with per-state counts plus explicit
  `exclusion_total` and `quarantine_total`.

Identical inputs rebuild byte-identically.
