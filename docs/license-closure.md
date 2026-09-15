# Source-license closure

Positive corpus publication is fail-closed on source-repository licensing.

Every released positive trajectory must resolve through all three of:

1. Frozen source-inventory license evidence (SPDX id or `LicenseRef-*` plus a
   content digest);
2. Snapshot provenance (`snapshot_sha256` and the repository `source_hash`);
3. Dataset-card disclosure (`source_license` / `source_licenses`, and a
   `License / provenance` section when a markdown card is supplied). Markdown
   disclosure must name the complete identifier; a prefix such as `MIT` does
   not satisfy `MIT-0`. `LicenseRef-*` custom evidence must use the same
   identifier as the inventory license.

Card, manifest, and inventory declarations must agree. Singular and
per-repository maps in the same artifact must not disagree. Missing, unknown,
conflicting, or changed evidence quarantines the row. Quarantined rows keep the
evidence they have and an explicit reason code. The closure manifest reports
license families, per-repository evidence digests, and unresolved counts.

This check does **not** decide license compatibility, relicense source-derived
material under Operation Prometheus's Apache-2.0 terms, or guess a license
when GitHub reports `NOASSERTION` / `OTHER`. A source repository that is
itself Apache-2.0 can still close; using this forge's Apache-2.0 license to
fill a missing source license cannot.

Validation is deterministic and uses only frozen local files. It does not
contact GitHub.

## Run

```bash
python scripts/validate_license_closure.py \
  --records datasets/jsonl/<name>.jsonl \
  --card datasets/cards/<name>.json \
  --manifest datasets/manifests/<name>.manifest.json \
  --inventory datasets/inventory/v0.7/repositories.jsonl \
  --inventory-manifest datasets/inventory/v0.7/manifest.json \
  --markdown-card datasets/cards/<name>-trajectories-v0.md \
  --out /tmp/license-closure.json
```

Exit status 0 means every proposed positive closed. Exit status 1 means at
least one unresolved row would otherwise have entered the released-positive
set; those rows appear only under `quarantined`.

Pass `--prior-inventory` to compare a previous frozen repositories JSONL and
treat a digest or SPDX change as `source_license_changed`. If both
`--snapshot-sha256` and `--inventory-manifest` are supplied, they must name the
same snapshot digest.

## Schema

`schemas/license_closure.schema.json` (`license_closure_manifest_v1`).
