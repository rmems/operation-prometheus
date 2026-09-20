"""Released and quarantined rows for license-closure evaluation."""

from __future__ import annotations

from typing import Any

from .license_closure_eval_state import EvalAcc
from .license_closure_ids import CLOSED_FAMILIES, LICENSE_FAMILIES, UNRESOLVED_REASONS
from .license_closure_inventory import source_provenance_digest


def _primary_reason(reasons: list[str]) -> str:
    for code in UNRESOLVED_REASONS:
        if code in reasons:
            return code
    return reasons[0]


def _evidence_blob(acc: EvalAcc) -> dict[str, Any]:
    return {
        "card_license": acc.declared_card,
        "custom_license": acc.custom_license_obj,
        "declared_evidence_digest": acc.declared_digest,
        "evidence_digest": acc.digest,
        "inventory_license": acc.inventory_license,
        "manifest_license": acc.declared_manifest,
        "prior_evidence_digest": acc.prior_digest,
        "record_license": acc.declared_record,
        "repository_source_hash": acc.source_hash,
        "snapshot_sha256": acc.snapshot_sha256,
    }


def finish_eval(acc: EvalAcc) -> dict[str, Any]:
    acc.reasons = sorted(set(acc.reasons))
    evidence = _evidence_blob(acc)
    closed = not acc.reasons and acc.family in CLOSED_FAMILIES and acc.digest is not None
    if closed:
        return _released_row(acc, evidence)
    return _quarantine_row(acc, evidence)


def _released_row(acc: EvalAcc, evidence: dict[str, Any]) -> dict[str, Any]:
    assert acc.source_hash is not None
    assert acc.digest is not None
    released: dict[str, Any] = {
        "evidence_digest": acc.digest,
        "license_family": acc.family,
        "pr_number": acc.pr_number,
        "record_id": acc.rid,
        "repo": acc.repo,
        "spdx_id": acc.inventory_id or acc.declared_record or acc.declared_card,
        "state": "released_positive",
        "repository_source_hash": acc.source_hash,
        "snapshot_sha256": acc.snapshot_sha256,
        "source_provenance_digest": source_provenance_digest(
            acc.repo,
            acc.source_hash,
            acc.snapshot_sha256,
            {
                "record_id": acc.rid,
                "pr_number": acc.pr_number,
                "evidence_digest": acc.digest,
            },
        ),
        "evidence": evidence,
    }
    if acc.custom_license_obj is not None:
        released["custom_license"] = acc.custom_license_obj
    if acc.inventory_license is not None:
        released["inventory_license"] = acc.inventory_license
    return released


def _quarantine_row(acc: EvalAcc, evidence: dict[str, Any]) -> dict[str, Any]:
    reasons = acc.reasons or ["source_license_unresolved"]
    family = acc.family if acc.family in LICENSE_FAMILIES else "unknown"
    return {
        "evidence": evidence,
        "license_family": family,
        "pr_number": acc.pr_number,
        "primary_reason": _primary_reason(reasons),
        "reason_codes": reasons,
        "record_id": acc.rid,
        "repo": acc.repo,
        "state": "quarantined",
    }


def _evidence_from_row(row: dict[str, Any]) -> dict[str, Any]:
    custom = row.get("custom_license")
    frozen_custom = custom if isinstance(custom, dict) else None
    inventory = row.get("inventory_license")
    frozen_inventory = inventory if isinstance(inventory, dict) else None
    existing = row.get("evidence")
    if isinstance(existing, dict):
        evidence = dict(existing)
        evidence.setdefault("custom_license", frozen_custom)
        evidence.setdefault("inventory_license", frozen_inventory)
        return evidence
    acc = EvalAcc(
        record={},
        card={},
        manifest={},
        inventory_index={},
        prior_index=None,
        pull_requests=None,
        snapshot_sha256=row.get("snapshot_sha256") or "",
        markdown=None,
        declared_digest=None,
        digest=row.get("evidence_digest"),
        inventory_license=frozen_inventory,
        prior_digest=None,
        declared_record=None,
        declared_card=None,
        declared_manifest=None,
        source_hash=row.get("repository_source_hash"),
        custom_license_obj=frozen_custom,
    )
    return _evidence_blob(acc)


def duplicate_id_row(row: dict[str, Any]) -> dict[str, Any]:
    reasons = sorted(
        set(list(row.get("reason_codes") or []) + ["source_license_unresolved"])
    )
    family = row.get("license_family")
    return {
        "evidence": _evidence_from_row(row),
        "license_family": family if family in LICENSE_FAMILIES else "unknown",
        "pr_number": row.get("pr_number"),
        "primary_reason": _primary_reason(reasons),
        "reason_codes": reasons,
        "record_id": row["record_id"],
        "repo": row.get("repo") or "",
        "state": "quarantined",
    }
