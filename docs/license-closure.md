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
per-repository maps in the same artifact must not disagree, including the same
repository named twice under different casing. A `license_evidence_digest` that
is present but not a valid SHA-256 quarantines as `declarations_disagree`;
omitting the digest remains optional. Missing, unknown, conflicting, or changed
evidence quarantines the row. Quarantined rows keep the evidence they have and
an explicit reason code. Publication consumers must treat a report as closed
only when the quarantined array is empty, counts match those array lengths
(including `record_count` equal to released plus quarantined), and
`bundle_errors` is empty.

This check does **not** decide license compatibility, relicense source-derived
material under Operation Prometheus's Apache-2.0 terms, or guess a license
when GitHub reports `NOASSERTION` / `OTHER`. Unbalanced SPDX parentheses,
empty expression operands (`MIT OR ()`), and non-`LicenseRef-*` identifiers
stay unknown even if custom text evidence is present. A source repository that
is itself Apache-2.0 can still close; using this forge's Apache-2.0 license to
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
treat a digest or SPDX change as `source_license_changed`. Evidence digests
cover only `license` and `custom_license` objects, so a repository rename
expressed through inventory aliases does not look like a license change. Prior
inventory lookup also follows the current row's aliases, so a forward rename
still sees a license change on the previous name. If both `--snapshot-sha256`
and `--inventory-manifest` are supplied, they must name the same snapshot
digest. The dataset manifest must declare a valid `sha256` of `--records`; a
missing or malformed digest fails closed.

When a caller supplies a frozen pull-request inventory, every proposed record
must appear in that list. Duplicate repository+PR keys in that inventory are
rejected. Record `base_oid` / `head_oid` / merge `commit_oid` values on the
record's repository state are compared to the matching PR roles; a correct
base OID does not mask an incorrect head. Intermediate event `code_state`
commits and trajectory `tree_oid` values are not compared to those commit
OIDs. Omitting the pull-request inventory keeps repository-level snapshot
checks only. Top-level `repo` and `repository.owner`/`name` must agree when
both are present.

The closure manifest reports license families, per-repository evidence
digests, and unresolved counts.

## Schema

`schemas/license_closure.schema.json` (`license_closure_manifest_v1`).
