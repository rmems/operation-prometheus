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
   identifier as the inventory license. If `custom_license` declares both
   `identifier` and `spdx_id`, those fields must agree.

Card, manifest, and inventory declarations must agree. Singular and
per-repository maps in the same artifact must not disagree, including the same
repository named twice under different casing. A `license_evidence_digest` that
is present but not a valid SHA-256 quarantines as `declarations_disagree`;
omitting the digest remains optional. Missing, unknown, conflicting, or changed
evidence quarantines the row. Quarantined rows keep the evidence they have,
including a frozen `custom_license` object when the inventory row carried
one, and an explicit reason code. Quarantined evidence always includes
`custom_license` (`null` when there is no custom object). Duplicate
released IDs that are converted to quarantined rows keep their
`inventory_license` object. Publication consumers must treat a report as closed
only when the quarantined array is empty, counts match those array lengths
(including `record_count` equal to released plus quarantined), `bundle_errors`
is empty, and every released row's repository, digest, family, and identifier
appear in `evidence_digests` / `license_families`, released record IDs are
unique, and each released identifier still classifies as a closed family.
`released_positives` and `quarantined` must be arrays of objects; a
non-object quarantined entry cannot be dropped to fake a closed report.
Rows missing `record_id`, or quarantined rows missing `primary_reason` /
`reason_codes`, fail closed instead of raising `KeyError`.
Released rows missing `repo`, `license_family`, or `evidence_digest` fail
closed instead of raising `KeyError` while building the evidence summary.
Released rows persist `snapshot_sha256`, `repository_source_hash`, and a
`source_provenance_digest` bound to the record id, pull-request number,
repository name, and those hashes; swapping the published `repo`, `record_id`,
`pr_number`, or the report snapshot without that binding fails closed.
`closed` must be an actual boolean (`type is bool`); a string such as
`"false"` cannot stand in for the derived closure state.
Report count fields must be actual integers (`type is int`);
booleans such as `true`/`false` cannot stand in for `1`/`0`.
Manifest count fields must be actual integers; fractional values such as
`0.5` fail closed. A present `records` array, including `[]`, must enumerate
every evaluated row. Every listed entry must be an object with a non-empty
string `id`; extra `{}` or non-object values cannot be dropped.

This check does **not** decide license compatibility, relicense source-derived
material under Operation Prometheus's Apache-2.0 terms, or guess a license
when GitHub reports `NOASSERTION` / `OTHER`. Unbalanced SPDX parentheses,
empty expression operands (`MIT OR ()`), and non-`LicenseRef-*` identifiers
stay unknown even if custom text evidence is present. Grouped SPDX
expressions such as `(MIT OR Apache-2.0) AND BSD-3-Clause` remain SPDX;
adjacent grouped operands (`(MIT) OR (Apache-2.0)`) remain SPDX;
adjacent groups without an operator (`(MIT)(Apache-2.0)`) stay unknown
instead of recursing forever. Misplaced parentheses
(`MIT ( AND Apache-2.0)`) stay unknown. `WITH`
expressions stay unknown, including a parenthesized operand
(`MIT WITH Apache-2.0`, `MIT WITH (Apache-2.0)`). A
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
matches the file bytes. Every publication run requires that inventory-manifest
file binding; `--snapshot-sha256` without `--inventory-manifest` cannot close,
including inventories that declare no aliases. A fabricated repository row
with a newly computed `source_hash` is not authenticated by the snapshot
digest alone. Accepted snapshot digests are stored as lowercase hex.
The dataset manifest must declare a valid `sha256` of `--records`; a missing
or malformed digest fails closed. Duplicate inventory aliases that point at
different repositories are rejected. Duplicate immutable `repository_id`
values that point at different names are rejected. A present but unparseable
singular `source_license` (for example `{}`) cannot be ignored in favor of a
matching per-repository map. A present non-object plural map such as
`source_licenses: []` cannot be ignored in favor of a valid singular.
A present non-array `source_repos` value such as `{}`, or a list that
contains a non-string or blank element, cannot be ignored in favor of a
valid singular `source_repo`. A present non-string or blank singular
`source_repo` (for example `{}`) cannot be ignored in favor of a valid
`source_repos` list. A declared repository that is absent from the
inventory cannot close, even when card and manifest name the same unknown
repository.
Card and manifest must each name at least one source repository through
`source_repo` or a non-empty `source_repos` list. Omitting both keys, or
supplying only `source_repos: []`, quarantines as `declarations_disagree`.
Card and manifest `license_families` / `unresolved_license_count` must agree
with closed evidence when they are declared. Non-string family elements such
as `["spdx", 1]` or `[{}]` fail closed as a bundle error instead of raising. When both
artifacts declare `source_repo` / `source_repos`, the complete normalized
sets must agree after alias resolution; membership of the current record
alone is not enough. Card and manifest `source_licenses` /
`license_evidence_digests` maps are compared for every declared repository,
not only repositories that have a proposed record. Prior-inventory rows must
authenticate `source_hash` before their license is trusted. When the current
row carries `repository_id`, prior lookup matches that immutable id and does
not fall back to a reused GitHub name. Card and manifest declaration maps are
resolved through inventory aliases. Markdown disclosure ignores HTML comments,
fenced code blocks, hidden raw HTML (`<span hidden>MIT</span>`), non-rendered
`script` / `style` / `template` content, link destinations, and reference
definitions, so a URL that only contains `MIT`, including a destination with
balanced parentheses such as `https://example.test/foo(bar)/MIT`, or a fenced
`## License / provenance` heading, is not disclosure. A CommonMark
reference-definition title on the following line is stripped with the
definition. HTML comments and
non-rendered HTML are stripped before the license heading is located, so a
commented-out `## License / provenance` block cannot disclose a later
visible identifier. A void tag such as `<br/>` inside a hidden block
cannot close that hidden scope. Visible markup such as
`<p>MIT</p>` still counts. Disclosure stops the license section at the next
H1 or H2 heading, including CommonMark headings indented by up to three
spaces.
Released rows persist the inventory `license` object so publication can
recompute the evidence digest; swapping a custom `text_sha256` or an SPDX
`spdx_id` / `evidence_digest` while keeping the other bound fields fails
closed.
`build_manifest.py` copies license-closure fields from the card when they are
present. It copies `source_repo` only when the card declares a non-blank
singular name, so a plural-only `source_repos` card does not emit a blank
`source_repo` that would fail coverage.

When a caller supplies a frozen pull-request inventory, every proposed record
must appear in that list. Each row must include a `source_hash` bound to the
published object (canonical JSON of the row without `source_hash`). That
digest authenticates the OIDs used for code-state matching; it is not the
eligibility producer hash, which binds unsanitized GraphQL title/body the
published row does not keep. Missing or stale PR hashes are rejected.
Every supplied PR inventory row must be an object with a repository name, PR
number, and authenticated hash; a valid matching row plus a malformed `{}`
entry is rejected. Duplicate repository+PR keys in that inventory are rejected. Record
`base_oid` / `head_oid` / merge `commit_oid` values on the record's
repository state are compared to the matching PR roles after normalizing
accepted hexadecimal OIDs to lowercase. Only full Git object IDs are
accepted (40-character SHA-1 or 64-character SHA-256); truncated values
such as `abc` cannot close. A present malformed `base_oid` or `head_oid`
is not treated as absent: a matching merge OID cannot close over invalid
declared roles. A correct base OID
does not mask an incorrect head. A supplied PR inventory also requires a
valid inventory `merge_commit_oid` and a matching record merge role. A
record merge/commit OID is not compared to the PR head; missing merge
evidence fails closed. Intermediate event
`code_state` commits and trajectory `tree_oid` values are not compared to
those commit OIDs. Pull-request lookup follows inventory aliases, so a
canonical PR row still matches a trajectory that uses an old name. Conflicting
PR rows for a repository and one of its aliases at the same number are
rejected. When both the inventory repository and the PR row declare
`repository_id`, those immutable ids must match; a reused name with a
different id cannot close, including when a canonical PR row matches and an
alias PR row for the same number declares a different id.
Omitting the pull-request inventory keeps repository-level snapshot checks only.
Top-level `repo` and `repository.owner`/`name` must agree when both are
present.

The closure manifest reports license families, per-repository evidence
digests, and unresolved counts.

## Schema

`schemas/license_closure.schema.json` (`license_closure_manifest_v1`).
