"""License-closure report assembly and positive-release gates."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .license_closure_eval import _duplicate_id_row, _evaluate_record
from .license_closure_ids import (
    LICENSE_FAMILIES,
    SCHEMA_VERSION,
    _closed_release_family,
    _same_license,
    _sha256_or_none,
    _text,
    normalize_license_id,
)
from .license_closure_inventory import (
    evidence_digest,
    index_repositories,
    inventory_has_custom_evidence,
    license_evidence_payload,
    source_provenance_digest,
)
from .license_closure_pr import _index_pull_requests


def _declared_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _released_evidence_summary(
    released: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    families = sorted({row["license_family"] for row in released})
    keys = sorted(
        {
            (
                row["repo"],
                row["evidence_digest"],
                row["license_family"],
                row.get("spdx_id") or "",
            )
            for row in released
        }
    )
    evidence = [
        {
            "digest": digest,
            "family": family,
            "repository": repo,
            "spdx_id": spdx_id or None,
        }
        for repo, digest, family, spdx_id in keys
    ]
    return families, evidence


def _declared_families_invalid(declared: Any, expected: list[str]) -> bool:
    if not isinstance(declared, list):
        return True
    if any(
        not isinstance(item, str) or item not in LICENSE_FAMILIES for item in declared
    ):
        return True
    return sorted(declared) != expected


def _bundle_declaration_errors(
    report: dict[str, Any], manifest: dict[str, Any], card: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for source in (card, manifest):
        declared_families = source.get("license_families")
        if declared_families is None:
            continue
        if _declared_families_invalid(declared_families, report["license_families"]):
            errors.append(
                "card/manifest license_families do not agree with closed evidence"
            )
            break
    for source, label in ((card, "card"), (manifest, "manifest")):
        unresolved = source.get("unresolved_license_count")
        if unresolved is None:
            continue
        if _declared_count(unresolved) != report["counts"]["unresolved_count"]:
            errors.append(
                f"{label} unresolved_license_count does not agree with closure result"
            )
    declared_digests = manifest.get("license_evidence_digests")
    if isinstance(declared_digests, dict):
        observed = {
            row["repository"].casefold(): row["digest"]
            for row in report["evidence_digests"]
        }
        for repo, digest in declared_digests.items():
            actual = observed.get(_text(repo).casefold())
            if actual is not None and _sha256_or_none(digest) != actual:
                errors.append(
                    f"manifest evidence digest for {repo} does not agree with inventory"
                )
    if "record_count" in manifest:
        declared_count = _declared_count(manifest["record_count"])
        if declared_count != report["counts"]["record_count"]:
            errors.append("manifest record_count does not agree with proposed records")
    if "records" in manifest:
        listed = manifest.get("records")
        actual_ids = sorted(
            row["record_id"]
            for row in report["released_positives"] + report["quarantined"]
        )
        declared_ids: list[str] = []
        malformed = not isinstance(listed, list)
        if isinstance(listed, list):
            for row in listed:
                rid = _text(row.get("id")) if isinstance(row, dict) else ""
                if not rid:
                    malformed = True
                    break
                declared_ids.append(rid)
        if malformed or sorted(declared_ids) != actual_ids:
            errors.append("manifest record ids do not agree with proposed records")
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
    digest = _sha256_or_none(snapshot_sha256)
    if digest is None:
        raise ValueError("snapshot_sha256 must be a 64-character hex digest")
    snapshot_sha256 = digest
    inventory_index = index_repositories(repositories)
    prior_index = (
        index_repositories(prior_repositories)
        if prior_repositories is not None
        else None
    )
    pr_index = None if pull_requests is None else _index_pull_requests(pull_requests)
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
    id_counts = Counter(row["record_id"] for row in evaluated)
    evaluated = [
        _duplicate_id_row(row) if id_counts[row["record_id"]] > 1 else row
        for row in evaluated
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
    families, evidence = _released_evidence_summary(released)
    report = {
        "closed": not quarantined,
        "counts": {
            "quarantined_count": len(quarantined),
            "record_count": len(evaluated),
            "released_positive_count": len(released),
            "unresolved_count": len(quarantined),
        },
        "evidence_digests": evidence,
        "license_families": families,
        "quarantined": quarantined,
        "released_positives": released,
        "schema_version": SCHEMA_VERSION,
        "snapshot_sha256": snapshot_sha256,
    }
    report["bundle_errors"] = _bundle_declaration_errors(report, manifest, card)
    if report["bundle_errors"]:
        report["closed"] = False
    return report


def released_positive_ids(report: dict[str, Any]) -> list[str]:
    return [row["record_id"] for row in report.get("released_positives") or []]


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _released_row_types_valid(row: dict[str, Any]) -> bool:
    pr_number = row.get("pr_number")
    if pr_number is not None and type(pr_number) is not int:
        return False
    if any(
        not _nonempty_str(row.get(key))
        for key in (
            "record_id",
            "repo",
            "license_family",
            "evidence_digest",
            "repository_source_hash",
            "snapshot_sha256",
            "source_provenance_digest",
        )
    ):
        return False
    spdx_id = row.get("spdx_id")
    if spdx_id is not None and not isinstance(spdx_id, str):
        return False
    state = row.get("state")
    if state is not None and not isinstance(state, str):
        return False
    inventory = row.get("inventory_license")
    if inventory is not None and not isinstance(inventory, dict):
        return False
    custom = row.get("custom_license")
    if custom is not None and not isinstance(custom, dict):
        return False
    return True


def _released_evidence_bound(row: dict[str, Any], report_snapshot: str | None) -> bool:
    snapshot = _sha256_or_none(row.get("snapshot_sha256"))
    source_hash = _sha256_or_none(row.get("repository_source_hash"))
    if snapshot is None or source_hash is None or snapshot != report_snapshot:
        return False
    if _sha256_or_none(row.get("source_provenance_digest")) != source_provenance_digest(
        _text(row.get("repo")),
        source_hash,
        snapshot,
        record_id=_text(row.get("record_id")),
        pr_number=row.get("pr_number") if type(row.get("pr_number")) is int else None,
    ):
        return False
    reconstructed = {
        "custom_license": row.get("custom_license"),
        "license": row.get("inventory_license"),
    }
    has_custom = inventory_has_custom_evidence(reconstructed)
    family = row.get("license_family")
    if family == "custom":
        if not has_custom:
            return False
    elif has_custom:
        return False
    digest = _sha256_or_none(row.get("evidence_digest"))
    if digest != evidence_digest(license_evidence_payload(reconstructed)):
        return False
    return _same_license(
        normalize_license_id(row.get("inventory_license")),
        _text(row.get("spdx_id")),
    )


def _object_rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise AssertionError(f"{field} must contain only objects")
    return value


_RELEASED_ROW_KEYS = (
    "record_id",
    "repo",
    "license_family",
    "evidence_digest",
    "repository_source_hash",
    "snapshot_sha256",
    "source_provenance_digest",
)
_QUARANTINED_ROW_KEYS = ("record_id", "primary_reason", "reason_codes")


def _rows_with_keys(
    value: Any, field: str, required: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows = _object_rows(value, field)
    if any(key not in row or row[key] is None for row in rows for key in required):
        raise AssertionError(f"{field} rows are missing required fields")
    return rows


def _report_rows(
    report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    released = _rows_with_keys(
        report.get("released_positives"), "released_positives", _RELEASED_ROW_KEYS
    )
    quarantined = _rows_with_keys(
        report.get("quarantined"), "quarantined", _QUARANTINED_ROW_KEYS
    )
    return released, quarantined


def _derived_closed(report: dict[str, Any], quarantined: list[dict[str, Any]]) -> bool:
    return not quarantined and not (report.get("bundle_errors") or [])


def assert_released_positives_are_closed(report: dict[str, Any]) -> None:
    released, quarantined = _report_rows(report)
    if any(not _released_row_types_valid(row) for row in released):
        raise AssertionError("released row value types are invalid")
    leaked = sorted(
        {row["record_id"] for row in released}
        & {row["record_id"] for row in quarantined}
    )
    if leaked:
        raise AssertionError(
            "Unresolved records appeared in released positives: " + ", ".join(leaked)
        )
    if len({row.get("record_id") for row in released}) != len(released):
        raise AssertionError("Released record IDs are not unique")
    counts = report.get("counts") or {}
    if _declared_count(counts.get("unresolved_count")) != len(quarantined):
        raise AssertionError("Unresolved count drifted from quarantined rows")
    if _declared_count(counts.get("quarantined_count")) != len(quarantined):
        raise AssertionError("Quarantined count drifted from quarantined rows")
    if _declared_count(counts.get("released_positive_count")) != len(released):
        raise AssertionError("Released positive count does not match released rows")
    if _declared_count(counts.get("record_count")) != len(released) + len(quarantined):
        raise AssertionError(
            "Record count does not match released and quarantined rows"
        )
    if any(row.get("state") != "released_positive" for row in released):
        raise AssertionError("Non-positive row listed as released")
    closed = report.get("closed")
    if type(closed) is not bool or closed != _derived_closed(report, quarantined):
        raise AssertionError("closed does not match quarantined rows and bundle errors")
    families, evidence = _released_evidence_summary(released)
    if list(report.get("license_families") or []) != families:
        raise AssertionError("license_families do not match released rows")
    if list(report.get("evidence_digests") or []) != evidence:
        raise AssertionError("evidence_digests do not match released rows")
    report_snapshot = _sha256_or_none(report.get("snapshot_sha256"))
    if any(
        not _closed_release_family(
            row.get("spdx_id"),
            row.get("license_family"),
            has_custom_evidence=inventory_has_custom_evidence(
                {
                    "custom_license": row.get("custom_license"),
                    "license": row.get("inventory_license")
                    or {"spdx_id": row.get("spdx_id")},
                }
            ),
        )
        or not _released_evidence_bound(row, report_snapshot)
        for row in released
    ):
        raise AssertionError("released row license family is not closed")


def validate_positive_release(report: dict[str, Any]) -> list[str]:
    """Return human-readable errors that block positive publication."""
    errors: list[str] = []
    try:
        assert_released_positives_are_closed(report)
    except AssertionError as exc:
        errors.append(str(exc))
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            "license-closure manifest schema_version is not license_closure_manifest_v1"
        )
    for bundle_error in report.get("bundle_errors") or []:
        errors.append(f"license-closure manifest: {bundle_error}")
    try:
        _released, quarantined = _report_rows(report)
    except AssertionError as exc:
        message = str(exc)
        if message not in errors:
            errors.append(message)
        return errors
    if quarantined:
        errors.append(
            f"license closure is fail-closed: {len(quarantined)} unresolved record(s) "
            "cannot be published as positives"
        )
        for row in quarantined:
            try:
                errors.append(
                    f"  {row['record_id']} [{row['primary_reason']}] "
                    f"reasons={','.join(row['reason_codes'])}"
                )
            except (KeyError, TypeError):
                errors.append("  quarantined row is missing required fields")
    elif not _derived_closed(report, quarantined):
        errors.append(
            "license closure is fail-closed: bundle declarations do not agree"
        )
    return errors
