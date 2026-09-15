# Source-license closure

Positive corpus publication is fail-closed on source-repository licensing.

Every released positive trajectory must resolve through all three of:

1. Frozen source-inventory license evidence (SPDX id or `LicenseRef-*` plus a
   content digest);
2. Snapshot provenance (`snapshot_sha256` and a repository `source_hash` that
   matches the eligibility producer payload for that row: GitHub source fields
   such as license, ids, and timestamps, not aliases or `schema_version`);
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
(including `record_count` equal to released plus quarantined), `bundle_errors`
is empty, and every released row's repository, digest, family, and identifier
appear in `evidence_digests` / `license_families`, released record IDs are
unique, and each released identifier still classifies as a closed family.
Manifest count fields must be actual integers; fractional values such as
`0.5` fail closed. A present `records` array, including `[]`, must enumerate
every evaluated row.

This check does **not** decide license compatibility, relicense source-derived
material under Operation Prometheus's Apache-2.0 terms, or guess a license
when GitHub reports `NOASSERTION` / `OTHER`. Unbalanced SPDX parentheses,
empty expression operands (`MIT OR ()`), and non-`LicenseRef-*` identifiers
stay unknown even if custom text evidence is present. Grouped SPDX
expressions such as `(MIT OR Apache-2.0) AND BSD-3-Clause` remain SPDX;
adjacent grouped operands (`(MIT) OR (Apache-2.0)`) remain SPDX;
misplaced parentheses (`MIT ( AND Apache-2.0)`) stay unknown. `WITH`
expressions whose right
operand is a license identifier (`MIT WITH Apache-2.0`) stay unknown. A
source repository that is itself Apache-2.0 can still close; using this
forge's Apache-2.0 license to fill a missing source license cannot.

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

Exit status 0 means the report is closed. Exit status 1 means validation
completed but closure failed because records were quarantined or bundle
declarations were invalid.

Pass `--prior-inventory` to compare a previous frozen repositories JSONL and
treat a digest or SPDX change as `source_license_changed`. Evidence digests
cover only `license` and `custom_license` objects, so a repository rename
expressed through inventory aliases does not look like a license change. Prior
inventory lookup also follows the current row's aliases, so a forward rename
still sees a license change on the previous name. If both `--snapshot-sha256`
and `--inventory-manifest` are supplied, they must name the same snapshot
digest. A supplied inventory manifest must bind `--inventory` through a
`files` entry (`repositories.jsonl` or the inventory basename) whose `sha256`
matches the file bytes. Accepted snapshot digests are stored as lowercase hex.
The dataset manifest must declare a valid `sha256` of `--records`; a missing
or malformed digest fails closed. Duplicate inventory aliases that point at
different repositories are rejected. Duplicate immutable `repository_id`
values that point at different names are rejected. A present but unparseable
singular `source_license` (for example `{}`) cannot be ignored in favor of a
matching per-repository map. A present non-object plural map such as
`source_licenses: []` cannot be ignored in favor of a valid singular.
Card and manifest `license_families` / `unresolved_license_count` must agree
with closed evidence when they are declared. Non-string family elements such
as `["spdx", 1]` fail closed as a bundle error instead of raising. Prior-inventory rows must
authenticate `source_hash` before their license is trusted. When the current
row carries `repository_id`, prior lookup matches that immutable id and does
not fall back to a reused GitHub name. Card and manifest declaration maps are
resolved through inventory aliases. Markdown disclosure ignores HTML comments
and stops the license section at the next H1 or H2 heading.
`build_manifest.py` copies license-closure fields from the card when they are
present.

When a caller supplies a frozen pull-request inventory, every proposed record
must appear in that list. Each row must include a `source_hash` bound to the
published object (canonical JSON of the row without `source_hash`). That
digest authenticates the OIDs used for code-state matching; it is not the
eligibility producer hash, which binds unsanitized GraphQL title/body the
published row does not keep. Missing or stale PR hashes are rejected.
Duplicate repository+PR keys in that inventory are rejected. Record
`base_oid` / `head_oid` / merge `commit_oid` values on the record's
repository state are compared to the matching PR roles; a correct base OID
does not mask an incorrect head. A supplied PR inventory also requires a
valid inventory `merge_commit_oid` and a matching record merge role. A
record merge/commit OID is not compared to the PR head; missing merge
evidence fails closed. Intermediate event
`code_state` commits and trajectory `tree_oid` values are not compared to
those commit OIDs. Pull-request lookup follows inventory aliases, so a
canonical PR row still matches a trajectory that uses an old name. Conflicting
PR rows for a repository and one of its aliases at the same number are
rejected.
Omitting the pull-request inventory keeps repository-level snapshot checks only.
Top-level `repo` and `repository.owner`/`name` must agree when both are
present.

The closure manifest reports license families, per-repository evidence
digests, and unresolved counts.

## Schema

`schemas/license_closure.schema.json` (`license_closure_manifest_v1`).
