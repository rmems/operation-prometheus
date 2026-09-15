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
   not satisfy `MIT-0`. CommonMark ATX license headings keep heading whitespace
   on the same line (`## License / provenance`); an empty `##` followed by a
   `License / provenance` paragraph is not a heading. Optional ATX closing
   hashes (`## License / provenance ##`) still locate the section. `LicenseRef-*`
   custom evidence must use the same
   identifier as the inventory license. If `custom_license` declares both
   `identifier` and `spdx_id`, those fields must agree. If it declares both
   `text_sha256` and `evidence_sha256`, those digests must be valid and equal;
   a present mismatch cannot close by preferring `text_sha256`. An SPDX
   inventory row that also carries a `custom_license` object whose identifier
   does not match that SPDX license is quarantined as `source_license_conflict`
   instead of releasing with a digest that publication cannot reconstruct.
   Persisted SPDX released rows cannot add that unmatched object and close by
   recomputing `evidence_digest`, `source_provenance_digest`, and the evidence
   summary.

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
`inventory_license` object and the released row's `snapshot_sha256` /
`repository_source_hash`. A record whose `id` and `trajectory_id` are
absent, blank, or non-string is quarantined as `declarations_disagree`
instead of closing under a synthetic `repo#pr` identifier. A present `id` or
`trajectory_id` that is not a non-empty string (for example `id: 7`) cannot
close by falling back to the other identity. If both identifiers are present
as non-empty strings, they must be identical; conflicting `id` /
`trajectory_id` values quarantine as `declarations_disagree` instead of
silently preferring `id`.
A trajectory `license` must be a non-empty string; an object such as
`{"spdx_id": "MIT"}` cannot close by unwrapping `spdx_id`.
Publication consumers must treat a report as closed
only when the quarantined array is empty, counts match those array lengths
(including `record_count` equal to released plus quarantined), `counts` is a
present object (a truthy non-object such as `[1]` cannot crash the gate),
`bundle_errors`
is a present array of strings and is empty (omitting the key or substituting
`{}` cannot stand in for `[]`), `license_families` is a present array (a
truthy object such as `{"spdx": 123}` cannot stand in for `["spdx"]`),
`evidence_digests` is a present array (a truthy scalar such as `1` or `true`
cannot crash the gate), and every released row's repository, digest, family, and identifier
appear in `evidence_digests` / `license_families`, released record IDs are
unique, and each released identifier still classifies as a closed family.
Trajectory records passed to `build_license_closure_report` must all be
objects; a valid matching row plus a non-object `"not-a-row"` entry is
rejected instead of skipped. `released_positives` and `quarantined` must be
arrays of objects; a non-object quarantined entry cannot be dropped to fake a
closed report.
Rows missing `record_id`, or quarantined rows missing `primary_reason` /
`reason_codes`, fail closed instead of raising `KeyError`. Quarantined
`record_id` values must be strings; an array identifier cannot crash the
publication gate with `TypeError`.
Released rows missing `repo`, `license_family`, or `evidence_digest` fail
closed instead of raising `KeyError` while building the evidence summary.
Released rows persist `snapshot_sha256`, `repository_source_hash`, and a
`source_provenance_digest` bound to the record id, pull-request number,
repository name, `evidence_digest`, and those hashes; swapping the published
`repo`, `record_id`, `pr_number`, `evidence_digest` / inventory license, or
the report snapshot without that binding fails closed.
Released identity, family, and digest fields must be non-empty strings;
`pr_number` must be `null` or an integer `>= 1` (`type is int`, so `true`
cannot stand in for `1`, and `0` / `-1` cannot close after rebuilding
`source_provenance_digest`). A present record `pr_number` that is not an
integer `>= 1` (`true`, `0`, `"7"`) quarantines as `declarations_disagree`;
omitting the key or setting `null` remains allowed when no pull-request
inventory is supplied.
An integer `repo` such as `7` cannot close by rebuilding
`source_provenance_digest` and `evidence_digests`. Unhashable values such as
`[]` fail closed instead of raising `TypeError`.
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
instead of recursing forever. Deeply nested but balanced groups such as
repeated `MIT OR (...)` stay unknown once nesting exceeds the parser bound,
instead of raising `RecursionError`. Misplaced parentheses
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
treat a digest or SPDX change as `source_license_changed`. A supplied
`--prior-inventory` also requires `--prior-inventory-manifest` with a `files`
entry (`repositories.jsonl` or the prior basename) whose `sha256` matches the
prior file bytes; replacing an unbound prior file whose public per-row
`source_hash` matches the current license cannot suppress
`source_license_changed`. Evidence digests
cover only `license` and `custom_license` objects, so a repository rename
expressed through inventory aliases does not look like a license change. Prior
inventory lookup also follows the current row's aliases, so a forward rename
still sees a license change on the previous name. If both `--snapshot-sha256`
and `--inventory-manifest` are supplied, they must name the same snapshot
digest. A supplied inventory manifest must itself declare a valid
`snapshot_sha256`; `--snapshot-sha256` cannot fill a missing manifest digest
and is only used to confirm that frozen value. A supplied inventory manifest must bind `--inventory` through a
`files` entry (`repositories.jsonl` or the inventory basename) whose `sha256`
matches the file bytes. Every publication run requires that inventory-manifest
file binding; `--snapshot-sha256` without `--inventory-manifest` cannot close,
including inventories that declare no aliases. The checker reads each
publication artifact once and hashes those captured bytes, so a rewrite
between report construction and binding comparison cannot authenticate a
different file than the report describes. `--out` cannot resolve to the same
path as `--records`, `--card`, `--manifest`, `--inventory`,
`--inventory-manifest`, `--prior-inventory`, `--prior-inventory-manifest`, or
`--markdown-card`, including
through symlinks and hard links that share an inode; a colliding `--out` is
rejected before `--check` or write
so frozen inputs cannot be overwritten. `--card` and `--manifest` must be JSON
objects; an array or scalar root fails closed instead of raising
`AttributeError`. JSON parsers reject the non-finite
constants `NaN`, `Infinity`, and `-Infinity`; `render_json` writes with
`allow_nan=False`. `build_manifest.py` uses the same non-finite rejection when
loading cards and existing manifests, and `render` writes with
`allow_nan=False`, so a card `unresolved_license_count: NaN` cannot be copied
into a passing `--check`. Duplicate object keys in frozen JSON or JSONL (for
example `"license": "GPL-3.0-only"` later overwritten by `"license": "MIT"`)
are rejected instead of silently keeping the last value. A fabricated repository row
with a newly computed `source_hash` is not authenticated by the snapshot
digest alone. Producer-hash reconstruction rejects malformed coerced scalars
such as `archived: {}` or `pull_request_total_count: {}` instead of
authenticating them as `false` / `0`. Inventory rows must declare `visibility` as the exact string
`public` before `source_hash` is trusted; `private`, `internal`, or a missing
visibility cannot close even when the digest matches. Prior-inventory rows
use the same public-visibility authentication before a license change is
evaluated. Accepted snapshot digests are stored as lowercase hex.
The dataset manifest must declare a valid `sha256` of `--records`; a missing
or malformed digest fails closed. Duplicate inventory aliases that point at
different repositories are rejected. Inventory `aliases` must be an array of
names or `{name_with_owner}` objects; a JSON object such as
`{"rmems/other": {}}` cannot be indexed as a legitimate alias. Each alias
entry must be a non-empty name string or `{name_with_owner}` object;
`{}` or `7` cannot be skipped. Duplicate immutable `repository_id`
values that point at different names are rejected. Every supplied repository
inventory row must be an object with a non-empty canonical `name_with_owner`;
a valid matching row plus a malformed `{}` entry is rejected instead of
skipped. A present but unparseable
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
not only repositories that have a proposed record. Each declared repository
must resolve to a license in both artifacts; omitting an unused repository
from both `source_licenses` maps cannot close. Those declared licenses
and digests are also compared to the matching inventory row, so an unused
declared repository cannot close by agreeing with the other artifact while
disagreeing with frozen inventory evidence. Prior-inventory rows must
authenticate `source_hash` before their license is trusted. When the current
row carries `repository_id`, prior lookup matches that immutable id and does
not fall back to a reused GitHub name. Card and manifest declaration maps are
resolved through inventory aliases. Markdown disclosure ignores HTML comments,
fenced code blocks, hidden raw HTML (`<span hidden>MIT</span>`), inline CSS
that hides content (`style="display:none"` / `visibility:hidden`),
non-rendered `script` / `style` / `template` content, link destinations, and
reference definitions, so a URL that only contains `MIT`, including a
destination with balanced parentheses such as
`https://example.test/foo(bar)/MIT`, a nested link label such as
`[details [nested]](https://example.test/MIT)`, a nested image destination
such as `[![details](https://example.test/MIT)](https://outer.test)`, a
destination on the line after
`[source]:`, or a fenced `## License / provenance` heading, is not
disclosure. A CommonMark reference-definition title on the following line is
stripped with the definition. Labels parse backslash escapes, so
`[license\]]: https://example.test/MIT` is stripped as a definition rather
than leaving `MIT` in visible text. HTML comments and
non-rendered HTML are stripped before the license heading is located, so a
commented-out `## License / provenance` block cannot disclose a later
visible identifier. A void tag such as `<br/>` inside a hidden block
cannot close that hidden scope. A Markdown code span that only looks like a
closing `</span>` tag cannot close a hidden HTML span that still contains
`MIT`. Visible markup such as
`<p>MIT</p>` still counts; splitting the identifier across block tags
(`<p>MI</p><p>T</p>`) does not. Disclosure stops the license section at the
next H1 or H2 heading, including CommonMark ATX headings indented by up to
three spaces and Setext H1 (`===`) / H2 (`---`) underlines. A paragraph
followed by `---` is a Setext H2 and ends the section; a lone thematic break
with no title line does not. `###` headings do not bound the section.
Released rows persist the inventory `license` object so publication can
recompute the evidence digest; swapping a custom `text_sha256` or an SPDX
`spdx_id` / `inventory_license` / `evidence_digest` while keeping
`source_provenance_digest` fails closed.
`build_manifest.py` copies license-closure fields from the card when they are
present. It copies `source_repo` only when the card declares a non-blank
singular name, so a plural-only `source_repos` card does not emit a blank
`source_repo` that would fail coverage. Copied numeric fields cannot be the
non-finite JSON constants `NaN` / `Infinity` / `-Infinity`.

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
such as `abc` cannot close. Every present inventory PR `base_oid`,
`head_oid`, or `merge_commit_oid` must be a full Git object ID; truncated
inventory `base_oid` / `head_oid` values such as `abc` and `def` cannot
authenticate a record that only matches `merge_commit_oid`. A present
malformed `base_oid` or `head_oid`
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
present. A present non-string or blank top-level `repo` such as `7` cannot
be erased so the nested identity can close. A present malformed or incomplete
nested identity such as `repository: {"owner": 7, "name": "widget"}` cannot
be discarded so a valid top-level `repo` can close.

The closure manifest reports license families, per-repository evidence
digests, and unresolved counts.

## Schema

`schemas/license_closure.schema.json` (`license_closure_manifest_v1`).
