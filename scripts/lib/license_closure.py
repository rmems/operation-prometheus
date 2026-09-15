"""Fail-closed source-license closure for positive corpus release.

Every released positive trajectory must resolve through frozen source-repository
license evidence, snapshot provenance, and dataset-card disclosure. Missing,
unknown, conflicting, or changed evidence quarantines the row. Quarantined rows
keep their evidence and an explicit reason.

This module does not guess licenses, assess compatibility, or treat this
repository's Apache-2.0 license as a relicense of source-derived material.
Validation is deterministic and uses only caller-supplied frozen evidence.
"""

from __future__ import annotations

import re
from typing import Any

from .source_inventory_common import sha256_json

SCHEMA_VERSION = "license_closure_manifest_v1"
FORGE_LICENSE = "Apache-2.0"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-fA-F]{3,64}$")
LICENSE_REF_RE = re.compile(r"^LicenseRef-[A-Za-z0-9.-]+$")
EXPRESSION_SPLIT_RE = re.compile(r"\s+(?:AND|OR|WITH)\s+", re.IGNORECASE)
MARKDOWN_LICENSE_SECTION_RE = re.compile(
    r"^##\s+License\s*/\s*provenance\s*$",
    re.IGNORECASE | re.MULTILINE,
)

CLOSED_FAMILIES = frozenset({"spdx", "custom"})
LICENSE_FAMILIES = frozenset({"spdx", "custom", "missing", "unknown"})
UNRESOLVED_REASONS = (
    "source_license_missing",
    "source_license_unknown",
    "source_license_changed",
    "source_license_conflict",
    "snapshot_provenance_missing",
    "card_disclosure_missing",
    "declarations_disagree",
    "forge_license_substitution",
)

# Frozen SPDX identifiers. Unknown IDs fail closed instead of being guessed.
# Includes current SPDX ids and the deprecated GitHub license-API spellings.
SPDX_LICENSE_IDS = frozenset(
    {
        "0BSD",
        "AFL-3.0",
        "AGPL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-2.0",
        "Artistic-2.0",
        "BlueOak-1.0.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-3-Clause-Clear",
        "BSD-4-Clause",
        "BSL-1.0",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC0-1.0",
        "CDDL-1.0",
        "ECL-2.0",
        "EPL-1.0",
        "EPL-2.0",
        "EUPL-1.1",
        "EUPL-1.2",
        "GPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "ISC",
        "LGPL-2.1",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "LPPL-1.3c",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "MS-PL",
        "MulanPSL-2.0",
        "NCSA",
        "OFL-1.1",
        "OSL-3.0",
        "PostgreSQL",
        "Python-2.0",
        "Unlicense",
        "UPL-1.0",
        "WTFPL",
        "Zlib",
    }
)
UNKNOWN_LICENSE_IDS = frozenset(
    {
        "NOASSERTION",
        "NONE",
        "OTHER",
        "UNKNOWN",
        "UNLICENSED",
        "SEE LICENSE",
        "SEE-LICENSE",
    }
)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _sha256_or_none(value: Any) -> str | None:
    text = _text(value).lower()
    if SHA256_RE.fullmatch(text):
        return text
    return None


def normalize_license_id(value: Any) -> str | None:
    """Return a trimmed license identifier, or None when absent/non-string."""
    if isinstance(value, dict):
        for key in ("spdx_id", "id", "license"):
            found = normalize_license_id(value.get(key))
            if found is not None:
                return found
        return None
    text = _text(value)
    return text or None


def _expression_tokens(identifier: str) -> list[str]:
    stripped = identifier.strip()
    if not stripped:
        return []
    tokens = [
        token.strip("() ")
        for token in EXPRESSION_SPLIT_RE.split(stripped)
        if token.strip("() ")
    ]
    return tokens or [stripped]


def classify_license_family(identifier: str | None, *, has_custom_evidence: bool = False) -> str:
    """Classify a declared identifier without guessing a replacement license."""
    if identifier is None:
        return "missing"
    tokens = _expression_tokens(identifier)
    if not tokens:
        return "missing"
    upper_tokens = [token.upper() for token in tokens]
    if any(token in UNKNOWN_LICENSE_IDS for token in upper_tokens):
        if has_custom_evidence:
            return "custom"
        return "unknown"
    if any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        if all(
            token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token) for token in tokens
        ):
            return "custom"
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
    if has_custom_evidence:
        return "custom"
    return "unknown"


def inventory_license_object(repository: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(repository, dict):
        return None
    license_obj = repository.get("license")
    if isinstance(license_obj, dict):
        return {
            "spdx_id": license_obj.get("spdx_id"),
            "name": license_obj.get("name"),
            "url": license_obj.get("url"),
        }
    identifier = normalize_license_id(license_obj)
    if identifier is None:
        return None
    return {"spdx_id": identifier, "name": None, "url": None}


def inventory_has_custom_evidence(repository: dict[str, Any] | None) -> bool:
    if not isinstance(repository, dict):
        return False
    custom = repository.get("custom_license")
    if not isinstance(custom, dict):
        return False
    identifier = normalize_license_id(custom.get("identifier") or custom.get("spdx_id"))
    digest = _sha256_or_none(custom.get("text_sha256") or custom.get("evidence_sha256"))
    return bool(identifier and LICENSE_REF_RE.fullmatch(identifier) and digest)


def license_evidence_payload(
    repository: dict[str, Any],
    *,
    snapshot_sha256: str,
) -> dict[str, Any]:
    license_obj = inventory_license_object(repository) or {
        "spdx_id": None,
        "name": None,
        "url": None,
    }
    custom = repository.get("custom_license") if isinstance(repository.get("custom_license"), dict) else None
    return {
        "custom_license": custom,
        "license": license_obj,
        "name_with_owner": repository.get("name_with_owner"),
        "repository_source_hash": repository.get("source_hash"),
        "snapshot_sha256": snapshot_sha256,
    }


def evidence_digest(payload: dict[str, Any]) -> str:
    return sha256_json(payload)


def record_repo(record: dict[str, Any]) -> str:
    repo = _text(record.get("repo"))
    if repo:
        return repo
    repository = record.get("repository")
    if isinstance(repository, dict):
        owner = _text(repository.get("owner"))
        name = _text(repository.get("name"))
        if owner and name:
            return f"{owner}/{name}"
    return ""


def record_id(record: dict[str, Any]) -> str:
    for key in ("id", "trajectory_id"):
        value = _text(record.get(key))
        if value:
            return value
    repo = record_repo(record)
    pr_number = record.get("pr_number")
    if repo and isinstance(pr_number, int):
        return f"{repo.replace('/', '-')}#{pr_number}"
    return repo or "unknown-record"


def record_pr_number(record: dict[str, Any]) -> int | None:
    value = record.get("pr_number")
    if isinstance(value, int) and value >= 1:
        return value
    return None


def record_license(record: dict[str, Any]) -> str | None:
    return normalize_license_id(record.get("license"))


def _mapping_license(container: dict[str, Any], repo: str, singular: str, plural: str) -> str | None:
    mapped = container.get(plural)
    if isinstance(mapped, dict):
        for key in (repo, repo.casefold()):
            found = normalize_license_id(mapped.get(key))
            if found is not None:
                return found
    return normalize_license_id(container.get(singular))


def _mapping_digest(container: dict[str, Any], repo: str, singular: str, plural: str) -> str | None:
    mapped = container.get(plural)
    if isinstance(mapped, dict):
        for key in (repo, repo.casefold()):
            found = _sha256_or_none(mapped.get(key))
            if found is not None:
                return found
    return _sha256_or_none(container.get(singular))


def card_license_for_repo(card: dict[str, Any], repo: str) -> str | None:
    return _mapping_license(card, repo, "source_license", "source_licenses")


def manifest_license_for_repo(manifest: dict[str, Any], repo: str) -> str | None:
    return _mapping_license(manifest, repo, "source_license", "source_licenses")


def declared_digest_for_repo(container: dict[str, Any], repo: str) -> str | None:
    return _mapping_digest(
        container,
        repo,
        "license_evidence_digest",
        "license_evidence_digests",
    )


def index_repositories(repositories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in repositories:
        name = _text(row.get("name_with_owner"))
        if not name:
            continue
        folded = name.casefold()
        if folded in index:
            raise ValueError(f"Duplicate inventory repository {name}")
        index[folded] = row
        for alias in row.get("aliases") or []:
            if isinstance(alias, dict):
                alias_name = _text(alias.get("name_with_owner")).casefold()
            else:
                alias_name = _text(alias).casefold()
            if alias_name:
                index.setdefault(alias_name, row)
    return index


def _inventory_for_repo(
    index: dict[str, dict[str, Any]],
    repo: str,
) -> dict[str, Any] | None:
    return index.get(repo.casefold()) if repo else None


def _snapshot_oids(record: dict[str, Any], inventory_pr: dict[str, Any] | None) -> list[str]:
    oids: list[str] = []
    repository = record.get("repository")
    if isinstance(repository, dict):
        for key in ("base_oid", "head_oid", "commit_oid"):
            value = _text(repository.get(key))
            if value:
                oids.append(value)
    events = record.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            code_state = event.get("code_state")
            if not isinstance(code_state, dict):
                continue
            for key in ("base_oid", "head_oid", "commit_oid", "tree_oid"):
                value = _text(code_state.get(key))
                if value:
                    oids.append(value)
    if isinstance(inventory_pr, dict):
        for key in ("base_oid", "head_oid", "merge_commit_oid"):
            value = _text(inventory_pr.get(key))
            if value:
                oids.append(value)
    return oids


def _index_pull_requests(
    pull_requests: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in pull_requests or []:
        repo = _text(row.get("repository_name_with_owner")).casefold()
        number = row.get("number")
        if repo and isinstance(number, int):
            index[(repo, number)] = row
    return index


def _declared_repos(container: dict[str, Any]) -> set[str]:
    names = [_text(container.get("source_repo"))]
    extra = container.get("source_repos")
    if isinstance(extra, list):
        names.extend(_text(item) for item in extra)
    return {name.casefold() for name in names if name}


def _markdown_discloses(markdown: str | None, identifier: str | None) -> bool:
    if markdown is None:
        return True
    if not MARKDOWN_LICENSE_SECTION_RE.search(markdown):
        return False
    if identifier is None:
        return False
    return identifier.casefold() in markdown.casefold()


def _same_license(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return left.casefold() == right.casefold()


def _primary_reason(reasons: list[str]) -> str:
    for code in UNRESOLVED_REASONS:
        if code in reasons:
            return code
    return reasons[0]


def _evidence_blob(
    *,
    record_license: str | None,
    card_license: str | None,
    manifest_license: str | None,
    inventory_license: dict[str, Any] | None,
    digest: str | None,
    declared_digest: str | None,
    prior_digest: str | None,
    snapshot_sha256: str | None,
    repository_source_hash: str | None,
) -> dict[str, Any]:
    return {
        "card_license": card_license,
        "declared_evidence_digest": declared_digest,
        "evidence_digest": digest,
        "inventory_license": inventory_license,
        "manifest_license": manifest_license,
        "prior_evidence_digest": prior_digest,
        "record_license": record_license,
        "repository_source_hash": repository_source_hash,
        "snapshot_sha256": snapshot_sha256,
    }


def _evaluate_record(
    record: dict[str, Any],
    *,
    card: dict[str, Any],
    manifest: dict[str, Any],
    inventory_index: dict[str, dict[str, Any]],
    prior_index: dict[str, dict[str, Any]] | None,
    pull_requests: dict[tuple[str, int], dict[str, Any]],
    snapshot_sha256: str,
    markdown: str | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    repo = record_repo(record)
    rid = record_id(record)
    pr_number = record_pr_number(record)
    declared_record = record_license(record)
    declared_card = card_license_for_repo(card, repo)
    declared_manifest = manifest_license_for_repo(manifest, repo)
    repository = _inventory_for_repo(inventory_index, repo)
    inventory_license = inventory_license_object(repository)
    inventory_id = normalize_license_id(inventory_license)
    has_custom = inventory_has_custom_evidence(repository)
    family = classify_license_family(inventory_id, has_custom_evidence=has_custom)
    if family == "missing":
        family = classify_license_family(declared_record, has_custom_evidence=has_custom)

    source_hash = None
    digest = None
    if isinstance(repository, dict):
        source_hash = _sha256_or_none(repository.get("source_hash"))
        digest = evidence_digest(
            license_evidence_payload(repository, snapshot_sha256=snapshot_sha256)
        )

    card_digest = declared_digest_for_repo(card, repo)
    manifest_digest = declared_digest_for_repo(manifest, repo)
    declared_digest = card_digest or manifest_digest
    declared_digest_values = {
        item for item in (card_digest, manifest_digest) if item is not None
    }
    if len(declared_digest_values) > 1:
        reasons.append("declarations_disagree")
    prior_digest = None
    prior_id = None
    if prior_index is not None:
        prior_repo = _inventory_for_repo(prior_index, repo)
        if isinstance(prior_repo, dict):
            prior_id = normalize_license_id(inventory_license_object(prior_repo))
            prior_digest = evidence_digest(
                license_evidence_payload(prior_repo, snapshot_sha256=snapshot_sha256)
            )

    declared_repos = _declared_repos(card) | _declared_repos(manifest)
    if declared_repos and repo and repo.casefold() not in declared_repos:
        reasons.append("declarations_disagree")
    if not repo or repository is None:
        reasons.append("snapshot_provenance_missing")
    if not _sha256_or_none(snapshot_sha256) or source_hash is None:
        reasons.append("snapshot_provenance_missing")
    inventory_pr = None
    if repo and pr_number is not None:
        inventory_pr = pull_requests.get((repo.casefold(), pr_number))
    oids = _snapshot_oids(record, inventory_pr)
    if inventory_pr is not None and not any(GIT_OID_RE.fullmatch(oid) for oid in oids):
        reasons.append("snapshot_provenance_missing")

    if declared_card is None:
        reasons.append("card_disclosure_missing")
    if not _markdown_discloses(markdown, declared_card or inventory_id):
        reasons.append("card_disclosure_missing")

    identifiers = [declared_record, declared_card, declared_manifest, inventory_id]
    present = [item for item in identifiers if item is not None]
    if not present:
        reasons.append("source_license_missing")
        family = "missing"
    elif any(item is None for item in identifiers):
        reasons.append("source_license_missing")
        if family not in LICENSE_FAMILIES:
            family = "missing"

    if present and len({item.casefold() for item in present}) > 1:
        reasons.append("source_license_conflict")
        reasons.append("declarations_disagree")

    closed_family = classify_license_family(
        inventory_id or declared_record or declared_card,
        has_custom_evidence=has_custom,
    )
    if closed_family in {"missing"}:
        reasons.append("source_license_missing")
        family = "missing"
    elif closed_family == "unknown":
        reasons.append("source_license_unknown")
        family = "unknown"
    else:
        family = closed_family

    if (
        inventory_id is None or inventory_id.upper() in UNKNOWN_LICENSE_IDS
    ) and any(_text(item).casefold() == FORGE_LICENSE.casefold() for item in present):
        reasons.append("forge_license_substitution")

    if digest is not None and any(
        declared is not None and declared != digest
        for declared in (card_digest, manifest_digest)
    ):
        reasons.append("source_license_changed")
    if prior_digest is not None and digest is not None and prior_digest != digest:
        reasons.append("source_license_changed")
    if prior_id is not None and inventory_id is not None and not _same_license(prior_id, inventory_id):
        reasons.append("source_license_changed")

    reasons = sorted(set(reasons))
    evidence = _evidence_blob(
        record_license=declared_record,
        card_license=declared_card,
        manifest_license=declared_manifest,
        inventory_license=inventory_license,
        digest=digest,
        declared_digest=declared_digest,
        prior_digest=prior_digest,
        snapshot_sha256=snapshot_sha256,
        repository_source_hash=source_hash,
    )
    closed = not reasons and family in CLOSED_FAMILIES and digest is not None
    if closed:
        return {
            "evidence_digest": digest,
            "license_family": family,
            "pr_number": pr_number,
            "record_id": rid,
            "repo": repo,
            "spdx_id": inventory_id or declared_record or declared_card,
            "state": "released_positive",
        }
    return {
        "evidence": evidence,
        "license_family": family if family in LICENSE_FAMILIES else "unknown",
        "pr_number": pr_number,
        "primary_reason": _primary_reason(reasons or ["source_license_unresolved"]),
        "reason_codes": reasons or ["source_license_unresolved"],
        "record_id": rid,
        "repo": repo,
        "state": "quarantined",
    }


def _bundle_declaration_errors(report: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """Return bundle-level disagreements between declared and observed closure."""
    errors: list[str] = []
    declared_families = manifest.get("license_families")
    if declared_families is not None and sorted(declared_families) != report["license_families"]:
        errors.append("card/manifest license_families do not agree with closed evidence")
    unresolved = manifest.get("unresolved_license_count")
    if unresolved is not None and int(unresolved) != report["counts"]["unresolved_count"]:
        errors.append("manifest unresolved_license_count does not agree with closure result")
    declared_digests = manifest.get("license_evidence_digests")
    if isinstance(declared_digests, dict):
        observed = {
            row["repository"].casefold(): row["digest"] for row in report["evidence_digests"]
        }
        for repo, digest in declared_digests.items():
            actual = observed.get(_text(repo).casefold())
            if actual is not None and _sha256_or_none(digest) != actual:
                errors.append(f"manifest evidence digest for {repo} does not agree with inventory")
    return errors


def build_license_closure_report(
    records: list[dict[str, Any]],
    card: dict[str, Any],
    manifest: dict[str, Any],
    repositories: list[dict[str, Any]],
    *,
    snapshot_sha256: str,
    pull_requests: list[dict[str, Any]] | None = None,
    prior_repositories: list[dict[str, Any]] | None = None,
    markdown_card: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic license-closure manifest from frozen evidence."""
    if not _sha256_or_none(snapshot_sha256):
        raise ValueError("snapshot_sha256 must be a lowercase 64-character hex digest")
    inventory_index = index_repositories(repositories)
    prior_index = index_repositories(prior_repositories) if prior_repositories is not None else None
    pr_index = _index_pull_requests(pull_requests)
    evaluated = [
        _evaluate_record(
            record,
            card=card,
            manifest=manifest,
            inventory_index=inventory_index,
            prior_index=prior_index,
            pull_requests=pr_index,
            snapshot_sha256=snapshot_sha256,
            markdown=markdown_card,
        )
        for record in records
        if isinstance(record, dict)
    ]
    released = sorted(
        [row for row in evaluated if row["state"] == "released_positive"],
        key=lambda row: (row["record_id"], row["repo"]),
    )
    quarantined = sorted(
        [row for row in evaluated if row["state"] == "quarantined"],
        key=lambda row: (row["record_id"], row["repo"]),
    )
    released_ids = {row["record_id"] for row in released}
    if any(row["record_id"] in released_ids for row in quarantined):
        raise AssertionError("Unresolved record leaked into released positives")
    families = sorted({row["license_family"] for row in released})
    digests = sorted(
        {
            (row["repo"], row["evidence_digest"], row["license_family"], row.get("spdx_id") or "")
            for row in released
        }
    )
    report = {
        "closed": not quarantined,
        "counts": {
            "quarantined_count": len(quarantined),
            "record_count": len(evaluated),
            "released_positive_count": len(released),
            "unresolved_count": len(quarantined),
        },
        "evidence_digests": [
            {
                "digest": digest,
                "family": family,
                "repository": repo,
                "spdx_id": spdx_id or None,
            }
            for repo, digest, family, spdx_id in digests
        ],
        "license_families": families,
        "quarantined": quarantined,
        "released_positives": released,
        "schema_version": SCHEMA_VERSION,
        "snapshot_sha256": snapshot_sha256,
    }
    report["bundle_errors"] = _bundle_declaration_errors(report, manifest)
    if report["bundle_errors"]:
        report["closed"] = False
    return report


def released_positive_ids(report: dict[str, Any]) -> list[str]:
    return [row["record_id"] for row in report.get("released_positives") or []]


def assert_released_positives_are_closed(report: dict[str, Any]) -> None:
    released = set(released_positive_ids(report))
    quarantined = {row["record_id"] for row in report.get("quarantined") or []}
    leaked = sorted(released & quarantined)
    if leaked:
        raise AssertionError(
            "Unresolved records appeared in released positives: " + ", ".join(leaked)
        )
    if report["counts"]["unresolved_count"] != report["counts"]["quarantined_count"]:
        raise AssertionError("Unresolved count drifted from quarantined count")
    if report["counts"]["released_positive_count"] != len(released):
        raise AssertionError("Released positive count does not match released rows")
    if any(row.get("state") != "released_positive" for row in report.get("released_positives") or []):
        raise AssertionError("Non-positive row listed as released")


def validate_positive_release(report: dict[str, Any]) -> list[str]:
    """Return human-readable errors that block positive publication."""
    assert_released_positives_are_closed(report)
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("license-closure manifest schema_version is not license_closure_manifest_v1")
    for bundle_error in report.get("bundle_errors") or []:
        errors.append(f"license-closure manifest: {bundle_error}")
    if report["counts"]["unresolved_count"]:
        unresolved = report["counts"]["unresolved_count"]
        errors.append(
            f"license closure is fail-closed: {unresolved} unresolved record(s) "
            "cannot be published as positives"
        )
        for row in report.get("quarantined") or []:
            errors.append(
                f"  {row['record_id']} [{row['primary_reason']}] "
                f"reasons={','.join(row['reason_codes'])}"
            )
    elif not report.get("closed"):
        errors.append("license closure is fail-closed: bundle declarations do not agree")
    return errors
