"""Fail-closed assertions for released positive license-closure rows."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import SCHEMA_VERSION
from .license_closure_report_counts import (
    _assert_closed_flag,
    _assert_counts,
    _assert_released_families,
    _assert_row_identity,
    _assert_summaries,
    _bundle_error_strings,
    _derived_closed,
)
from .license_closure_report_rows import _report_rows


def assert_released_positives_are_closed(report: dict[str, Any]) -> None:
    released, quarantined = _report_rows(report)
    _assert_row_identity(released, quarantined)
    _assert_counts(report, released, quarantined)
    _assert_closed_flag(report, quarantined)
    _assert_summaries(report, released)
    _assert_released_families(report, released)


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
    bundle_errors = _bundle_error_strings(report)
    if bundle_errors is None:
        errors.append(
            "license-closure manifest bundle_errors must be an array of strings"
        )
    else:
        errors.extend(f"license-closure manifest: {item}" for item in bundle_errors)
    errors.extend(_quarantine_errors(report))
    return errors


def _quarantine_row_error(row: dict[str, Any]) -> str:
    try:
        return (
            f"  {row['record_id']} [{row['primary_reason']}] "
            f"reasons={','.join(row['reason_codes'])}"
        )
    except (KeyError, TypeError):
        return "  quarantined row is missing required fields"


def _quarantine_errors(report: dict[str, Any]) -> list[str]:
    try:
        _released, quarantined = _report_rows(report)
    except AssertionError as exc:
        return [str(exc)]
    if not quarantined:
        if not _derived_closed(report, quarantined):
            return ["license closure is fail-closed: bundle declarations do not agree"]
        return []
    errors = [
        f"license closure is fail-closed: {len(quarantined)} unresolved record(s) "
        "cannot be published as positives"
    ]
    errors.extend(_quarantine_row_error(row) for row in quarantined)
    return errors
