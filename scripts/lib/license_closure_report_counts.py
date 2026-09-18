"""Count, closed-flag, and summary assertions for license-closure reports."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import _sha256_or_none
from .license_closure_report_bundle import _declared_count, _released_evidence_summary
from .license_closure_report_rows import (
    _released_row_is_closed,
    _released_row_types_valid,
)

def _bundle_error_strings(report: dict[str, Any]) -> list[str] | None:
    if "bundle_errors" not in report:
        return None
    value = report["bundle_errors"]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return value


def _derived_closed(report: dict[str, Any], quarantined: list[dict[str, Any]]) -> bool:
    bundle_errors = _bundle_error_strings(report)
    return not quarantined and bundle_errors is not None and not bundle_errors


def _assert_row_identity(
    released: list[dict[str, Any]], quarantined: list[dict[str, Any]]
) -> None:
    if any(not _released_row_types_valid(row) for row in released):
        raise AssertionError("released row value types are invalid")
    leaked = sorted(
        {row["record_id"] for row in released} & {row["record_id"] for row in quarantined}
    )
    if leaked:
        raise AssertionError(
            "Unresolved records appeared in released positives: " + ", ".join(leaked)
        )
    if len({row.get("record_id") for row in released}) != len(released):
        raise AssertionError("Released record IDs are not unique")


def _assert_counts(
    report: dict[str, Any],
    released: list[dict[str, Any]],
    quarantined: list[dict[str, Any]],
) -> None:
    counts = report.get("counts")
    if not isinstance(counts, dict):
        raise AssertionError("counts must be an object")
    checks = (
        (counts.get("unresolved_count"), len(quarantined), "Unresolved count drifted from quarantined rows"),
        (counts.get("quarantined_count"), len(quarantined), "Quarantined count drifted from quarantined rows"),
        (counts.get("released_positive_count"), len(released), "Released positive count does not match released rows"),
        (counts.get("record_count"), len(released) + len(quarantined), "Record count does not match released and quarantined rows"),
    )
    for declared, expected, message in checks:
        if _declared_count(declared) != expected:
            raise AssertionError(message)
    if any(row.get("state") != "released_positive" for row in released):
        raise AssertionError("Non-positive row listed as released")


def _assert_closed_flag(report: dict[str, Any], quarantined: list[dict[str, Any]]) -> None:
    closed = report.get("closed")
    if type(closed) is not bool or closed != _derived_closed(report, quarantined):
        raise AssertionError("closed does not match quarantined rows and bundle errors")


def _assert_summaries(report: dict[str, Any], released: list[dict[str, Any]]) -> None:
    families, evidence = _released_evidence_summary(released)
    declared_families = report.get("license_families")
    if not isinstance(declared_families, list) or declared_families != families:
        raise AssertionError("license_families do not match released rows")
    declared_evidence = report.get("evidence_digests")
    if not isinstance(declared_evidence, list) or declared_evidence != evidence:
        raise AssertionError("evidence_digests do not match released rows")


def _assert_released_families(report: dict[str, Any], released: list[dict[str, Any]]) -> None:
    report_snapshot = _sha256_or_none(report.get("snapshot_sha256"))
    if report_snapshot is None:
        raise AssertionError("snapshot_sha256 must be a 64-character hex digest")
    if any(not _released_row_is_closed(row, report_snapshot) for row in released):
        raise AssertionError("released row license family is not closed")
