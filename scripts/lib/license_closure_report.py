"""License-closure report assembly and positive-release gates."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .license_closure_eval import _duplicate_id_row, _evaluate_record
from .license_closure_ids import SCHEMA_VERSION, _sha256_or_none, _text
from .license_closure_inventory import index_repositories
from .license_closure_pr import _index_pull_requests


def _bundle_declaration_errors(
    report: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    """Return bundle-level disagreements between declared and observed closure."""
    errors: list[str] = []
    declared_families = manifest.get("license_families")
    if (
        declared_families is not None
        and sorted(declared_families) != report["license_families"]
    ):
        errors.append(
            "card/manifest license_families do not agree with closed evidence"
        )
    unresolved = manifest.get("unresolved_license_count")
    if (
        unresolved is not None
        and int(unresolved) != report["counts"]["unresolved_count"]
    ):
        errors.append(
            "manifest unresolved_license_count does not agree with closure result"
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
        try:
            declared_count = int(manifest["record_count"])
        except (TypeError, ValueError):
            declared_count = -1
        if declared_count != report["counts"]["record_count"]:
            errors.append("manifest record_count does not agree with proposed records")
    listed = manifest.get("records")
    if isinstance(listed, list) and listed:
        declared_ids = sorted(
            _text(row.get("id"))
            for row in listed
            if isinstance(row, dict) and _text(row.get("id"))
        )
        actual_ids = sorted(
            row["record_id"]
            for row in report["released_positives"] + report["quarantined"]
        )
        if declared_ids and declared_ids != actual_ids:
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
    if not _sha256_or_none(snapshot_sha256):
        raise ValueError("snapshot_sha256 must be a lowercase 64-character hex digest")
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
    families = sorted({row["license_family"] for row in released})
    digests = sorted(
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


def _report_rows(
    report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    released = [
        row for row in (report.get("released_positives") or []) if isinstance(row, dict)
    ]
    quarantined = [
        row for row in (report.get("quarantined") or []) if isinstance(row, dict)
    ]
    return released, quarantined


def _derived_closed(report: dict[str, Any], quarantined: list[dict[str, Any]]) -> bool:
    return not quarantined and not (report.get("bundle_errors") or [])


def assert_released_positives_are_closed(report: dict[str, Any]) -> None:
    released, quarantined = _report_rows(report)
    leaked = sorted(
        {row["record_id"] for row in released}
        & {row["record_id"] for row in quarantined}
    )
    if leaked:
        raise AssertionError(
            "Unresolved records appeared in released positives: " + ", ".join(leaked)
        )
    counts = report.get("counts") or {}
    if counts.get("unresolved_count") != len(quarantined):
        raise AssertionError("Unresolved count drifted from quarantined rows")
    if counts.get("quarantined_count") != len(quarantined):
        raise AssertionError("Quarantined count drifted from quarantined rows")
    if counts.get("released_positive_count") != len(released):
        raise AssertionError("Released positive count does not match released rows")
    if counts.get("record_count") != len(released) + len(quarantined):
        raise AssertionError(
            "Record count does not match released and quarantined rows"
        )
    if any(row.get("state") != "released_positive" for row in released):
        raise AssertionError("Non-positive row listed as released")
    if bool(report.get("closed")) != _derived_closed(report, quarantined):
        raise AssertionError("closed does not match quarantined rows and bundle errors")


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
    _released, quarantined = _report_rows(report)
    if quarantined:
        errors.append(
            f"license closure is fail-closed: {len(quarantined)} unresolved record(s) "
            "cannot be published as positives"
        )
        for row in quarantined:
            errors.append(
                f"  {row['record_id']} [{row['primary_reason']}] "
                f"reasons={','.join(row['reason_codes'])}"
            )
    elif not _derived_closed(report, quarantined):
        errors.append(
            "license closure is fail-closed: bundle declarations do not agree"
        )
    return errors
