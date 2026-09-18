"""Released-row type and evidence binding checks."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import _closed_release_family, _same_license, _sha256_or_none, _text, normalize_license_id
from .license_closure_inventory import (
    evidence_digest,
    inventory_has_custom_evidence,
    license_evidence_payload,
    source_provenance_digest,
)

def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _released_pr_number(value: Any) -> int | None:
    if type(value) is int and value >= 1:
        return value
    return None


def _released_row_types_valid(row: dict[str, Any]) -> bool:
    pr_number = row.get("pr_number")
    if pr_number is not None and _released_pr_number(pr_number) is None:
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
        pr_number=_released_pr_number(row.get("pr_number")),
        evidence_digest=_sha256_or_none(row.get("evidence_digest")) or "",
    ):
        return False
    reconstructed = {
        "custom_license": row.get("custom_license"),
        "license": row.get("inventory_license"),
    }
    has_custom = inventory_has_custom_evidence(reconstructed)
    family = row.get("license_family")
    custom_present = isinstance(row.get("custom_license"), dict)
    if family == "custom":
        if not has_custom:
            return False
    elif has_custom or custom_present:
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
    if "record_id" in required and any(
        not isinstance(row.get("record_id"), str) for row in rows
    ):
        raise AssertionError(f"{field} record_id values must be strings")
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


def _released_row_is_closed(row: dict[str, Any], report_snapshot: str) -> bool:
    reconstructed = {
        "custom_license": row.get("custom_license"),
        "license": row.get("inventory_license") or {"spdx_id": row.get("spdx_id")},
    }
    return _closed_release_family(
        row.get("spdx_id"),
        row.get("license_family"),
        has_custom_evidence=inventory_has_custom_evidence(reconstructed),
    ) and _released_evidence_bound(row, report_snapshot)
