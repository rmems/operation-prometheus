"""Build the deterministic license-closure report."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .license_closure_eval import _duplicate_id_row, _evaluate_record
from .license_closure_eval_state import EvalAcc
from .license_closure_ids import SCHEMA_VERSION, _sha256_or_none
from .license_closure_inventory import index_repositories
from .license_closure_pr import _index_pull_requests
from .license_closure_report_bundle import (
    _bundle_declaration_errors,
    _released_evidence_summary,
)


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
    snapshot_sha256 = _require_snapshot(snapshot_sha256)
    _require_objects(card, manifest, records)
    evaluated = _evaluate_records(
        records,
        card,
        manifest,
        repositories,
        snapshot_sha256,
        pull_requests,
        prior_repositories,
        markdown_card,
    )
    released, quarantined = _partition_rows(evaluated)
    return _assemble_report(evaluated, released, quarantined, snapshot_sha256, card, manifest)


def _require_snapshot(snapshot_sha256: str) -> str:
    digest = _sha256_or_none(snapshot_sha256)
    if digest is None:
        raise ValueError("snapshot_sha256 must be a 64-character hex digest")
    return digest


def _require_objects(card: object, manifest: object, records: list[object]) -> None:
    if not isinstance(card, dict):
        raise ValueError("card must be an object")
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("trajectory records must be objects")


def _evaluate_records(
    records: list[dict[str, Any]],
    card: dict[str, Any],
    manifest: dict[str, Any],
    repositories: list[dict[str, Any]],
    snapshot_sha256: str,
    pull_requests: list[dict[str, Any]] | None,
    prior_repositories: list[dict[str, Any]] | None,
    markdown_card: str | None,
) -> list[dict[str, Any]]:
    inventory_index = index_repositories(repositories)
    prior_index = (
        index_repositories(prior_repositories) if prior_repositories is not None else None
    )
    pr_index = None if pull_requests is None else _index_pull_requests(pull_requests)
    evaluated = [
        _evaluate_record(
            EvalAcc(
                record=record,
                card=card,
                manifest=manifest,
                inventory_index=inventory_index,
                prior_index=prior_index,
                pull_requests=pr_index,
                snapshot_sha256=snapshot_sha256,
                markdown=markdown_card,
            )
        )
        for record in records
    ]
    id_counts = Counter(row["record_id"] for row in evaluated)
    return [
        _duplicate_id_row(row) if id_counts[row["record_id"]] > 1 else row
        for row in evaluated
    ]


def _partition_rows(
    evaluated: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    released = sorted(
        [row for row in evaluated if row["state"] == "released_positive"],
        key=lambda row: (row["record_id"], row["repo"]),
    )
    for row in released:
        row.pop("evidence", None)
    quarantined = sorted(
        [row for row in evaluated if row["state"] == "quarantined"],
        key=lambda row: (row["record_id"], row["repo"]),
    )
    released_ids = {row["record_id"] for row in released}
    if any(row["record_id"] in released_ids for row in quarantined):
        raise AssertionError("Unresolved record leaked into released positives")
    return released, quarantined


def _assemble_report(
    evaluated: list[dict[str, Any]],
    released: list[dict[str, Any]],
    quarantined: list[dict[str, Any]],
    snapshot_sha256: str,
    card: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
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
