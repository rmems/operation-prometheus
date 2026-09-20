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


def build_license_closure_report(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic license-closure manifest from frozen evidence.

    ``bundle`` carries ``records``, ``card``, ``manifest``, ``repositories``,
    and ``snapshot_sha256`` plus optional ``pull_requests``,
    ``prior_repositories``, and ``markdown_card``.
    """
    card = bundle.get("card")
    manifest = bundle.get("manifest")
    records = bundle.get("records")
    _require_objects(card, manifest, records)
    snapshot_sha256 = _require_snapshot(bundle.get("snapshot_sha256"))
    evaluated = _evaluate_records(
        records, {**bundle, "snapshot_sha256": snapshot_sha256}
    )
    released, quarantined = _partition_rows(evaluated)
    report = _assemble_report(evaluated, released, quarantined, snapshot_sha256)
    report["bundle_errors"] = _bundle_declaration_errors(report, manifest, card)
    if report["bundle_errors"]:
        report["closed"] = False
    return report


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
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError("trajectory records must be objects")


def _evaluate_record_acc(record: dict[str, Any], ctx: dict[str, Any]) -> EvalAcc:
    return EvalAcc(
        record=record,
        card=ctx["card"],
        manifest=ctx["manifest"],
        inventory_index=ctx["inventory_index"],
        prior_index=ctx["prior_index"],
        pull_requests=ctx["pr_index"],
        snapshot_sha256=ctx["snapshot_sha256"],
        markdown=ctx.get("markdown_card"),
    )


def _dedupe_evaluated(evaluated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_counts = Counter(row["record_id"] for row in evaluated)
    return [
        _duplicate_id_row(row) if id_counts[row["record_id"]] > 1 else row
        for row in evaluated
    ]


def _optional_index(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]] | None:
    if rows is None:
        return None
    return index_repositories(rows)


def _evaluate_records(
    records: list[dict[str, Any]], bundle: dict[str, Any]
) -> list[dict[str, Any]]:
    pull_requests = bundle.get("pull_requests")
    ctx = {
        "card": bundle["card"],
        "manifest": bundle["manifest"],
        "inventory_index": index_repositories(bundle.get("repositories") or []),
        "prior_index": _optional_index(bundle.get("prior_repositories")),
        "pr_index": (
            _index_pull_requests(pull_requests) if pull_requests is not None else None
        ),
        "snapshot_sha256": bundle["snapshot_sha256"],
        "markdown_card": bundle.get("markdown_card"),
    }
    evaluated = [
        _evaluate_record(_evaluate_record_acc(record, ctx)) for record in records
    ]
    return _dedupe_evaluated(evaluated)


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
) -> dict[str, Any]:
    families, evidence = _released_evidence_summary(released)
    return {
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


def released_positive_ids(report: dict[str, Any]) -> list[str]:
    return [row["record_id"] for row in report.get("released_positives") or []]
