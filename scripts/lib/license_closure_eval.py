"""Per-record source-license closure evaluation."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import (
    CLOSED_FAMILIES,
    FORGE_LICENSE,
    LICENSE_FAMILIES,
    UNKNOWN_LICENSE_IDS,
    UNRESOLVED_REASONS,
    _same_license,
    _sha256_or_none,
    _text,
    classify_license_family,
    normalize_license_id,
)
from .license_closure_inventory import (
    _authenticated_inventory_source_hash,
    _canonical_declared_repos,
    _declaration_map_conflicts,
    _declared_source_maps_conflict,
    _identity_names,
    _inventory_for_repo,
    _prior_repository,
    _supplied_record_id,
    card_license_for_repo,
    declared_digest_for_repo,
    evidence_digest,
    inventory_has_custom_evidence,
    inventory_license_object,
    license_evidence_payload,
    manifest_license_for_repo,
    source_provenance_digest,
    record_id,
    record_license,
    record_pr_number,
    record_pr_number_invalid,
    record_repo,
    record_repo_identities_conflict,
)
from .license_closure_pr import (
    _declared_repos,
    _markdown_discloses,
    _pr_inventory_reasons,
    _source_coverage_invalid,
)


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
    custom_license: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "card_license": card_license,
        "custom_license": custom_license,
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
    pull_requests: dict[tuple[str, int], dict[str, Any]] | None,
    snapshot_sha256: str,
    markdown: str | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    repo = record_repo(record)
    if record_repo_identities_conflict(record):
        reasons.append("declarations_disagree")
    rid = record_id(record)
    if not _supplied_record_id(record):
        reasons.append("declarations_disagree")
    pr_number = record_pr_number(record)
    if record_pr_number_invalid(record):
        reasons.append("declarations_disagree")
    declared_record = record_license(record)
    repository = _inventory_for_repo(inventory_index, repo)
    names = _identity_names(repository, repo)
    declared_card = card_license_for_repo(card, names)
    declared_manifest = manifest_license_for_repo(manifest, names)
    inventory_license = inventory_license_object(repository)
    inventory_id = normalize_license_id(inventory_license)
    has_custom = inventory_has_custom_evidence(repository)
    custom_license_obj: dict[str, Any] | None = None
    if has_custom and isinstance(repository, dict):
        custom = repository.get("custom_license")
        if isinstance(custom, dict):
            custom_license_obj = custom
    family = classify_license_family(inventory_id, has_custom_evidence=has_custom)
    if family == "missing":
        family = classify_license_family(
            declared_record, has_custom_evidence=has_custom
        )

    source_hash = None
    digest = None
    if isinstance(repository, dict):
        source_hash = _authenticated_inventory_source_hash(repository)
        digest = evidence_digest(license_evidence_payload(repository))

    card_digest = declared_digest_for_repo(card, names)
    manifest_digest = declared_digest_for_repo(manifest, names)
    declared_digest = card_digest or manifest_digest
    declared_digest_values = {
        item for item in (card_digest, manifest_digest) if item is not None
    }
    if len(declared_digest_values) > 1:
        reasons.append("declarations_disagree")
    if _declaration_map_conflicts(card, manifest, names):
        reasons.append("declarations_disagree")
    prior_digest = None
    prior_id = None
    if prior_index is not None:
        prior_repo = _prior_repository(prior_index, repository, repo)
        if isinstance(prior_repo, dict):
            if _authenticated_inventory_source_hash(prior_repo) is None:
                reasons.append("source_license_changed")
            else:
                prior_id = normalize_license_id(inventory_license_object(prior_repo))
                prior_digest = evidence_digest(license_evidence_payload(prior_repo))

    card_repos = _declared_repos(card)
    manifest_repos = _declared_repos(manifest)
    folded_names = {name.casefold() for name in names}
    if _source_coverage_invalid(card) or _source_coverage_invalid(manifest):
        reasons.append("declarations_disagree")
    if card_repos and not folded_names.intersection(card_repos):
        reasons.append("declarations_disagree")
    if manifest_repos and not folded_names.intersection(manifest_repos):
        reasons.append("declarations_disagree")
    declared_repos = card_repos | manifest_repos
    if _declared_source_maps_conflict(card, manifest, declared_repos, inventory_index):
        reasons.append("declarations_disagree")
    if any(
        _inventory_for_repo(inventory_index, repo) is None for repo in declared_repos
    ):
        reasons.append("declarations_disagree")
    if (
        card_repos
        and manifest_repos
        and _canonical_declared_repos(card_repos, inventory_index)
        != _canonical_declared_repos(manifest_repos, inventory_index)
    ):
        reasons.append("declarations_disagree")
    if not repo or repository is None:
        reasons.append("snapshot_provenance_missing")
    if not _sha256_or_none(snapshot_sha256) or source_hash is None:
        reasons.append("snapshot_provenance_missing")
    reasons.extend(
        _pr_inventory_reasons(record, names, pr_number, pull_requests, repository)
    )

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

    if (inventory_id is None or inventory_id.upper() in UNKNOWN_LICENSE_IDS) and any(
        _text(item).casefold() == FORGE_LICENSE.casefold() for item in present
    ):
        reasons.append("forge_license_substitution")

    if digest is not None and any(
        declared is not None and declared != digest
        for declared in (card_digest, manifest_digest)
    ):
        reasons.append("source_license_changed")
    if prior_digest is not None and digest is not None and prior_digest != digest:
        reasons.append("source_license_changed")
    if (
        prior_id is not None
        and inventory_id is not None
        and not _same_license(prior_id, inventory_id)
    ):
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
        custom_license=custom_license_obj,
    )
    closed = not reasons and family in CLOSED_FAMILIES and digest is not None
    if closed:
        released: dict[str, Any] = {
            "evidence_digest": digest,
            "license_family": family,
            "pr_number": pr_number,
            "record_id": rid,
            "repo": repo,
            "spdx_id": inventory_id or declared_record or declared_card,
            "state": "released_positive",
        }
        if custom_license_obj is not None:
            released["custom_license"] = custom_license_obj
        if inventory_license is not None:
            released["inventory_license"] = inventory_license
        assert source_hash is not None
        released["repository_source_hash"] = source_hash
        released["snapshot_sha256"] = snapshot_sha256
        released["source_provenance_digest"] = source_provenance_digest(
            repo,
            source_hash,
            snapshot_sha256,
            record_id=rid,
            pr_number=pr_number,
        )
        return released
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


def _duplicate_id_row(row: dict[str, Any]) -> dict[str, Any]:
    custom = row.get("custom_license")
    frozen_custom = custom if isinstance(custom, dict) else None
    inventory = row.get("inventory_license")
    frozen_inventory = inventory if isinstance(inventory, dict) else None
    existing = row.get("evidence")
    if isinstance(existing, dict):
        evidence = dict(existing)
        if "custom_license" not in evidence:
            evidence["custom_license"] = frozen_custom
        if "inventory_license" not in evidence:
            evidence["inventory_license"] = frozen_inventory
    else:
        evidence = _evidence_blob(
            record_license=None,
            card_license=None,
            manifest_license=None,
            inventory_license=frozen_inventory,
            digest=row.get("evidence_digest"),
            declared_digest=None,
            prior_digest=None,
            snapshot_sha256=row.get("snapshot_sha256"),
            repository_source_hash=row.get("repository_source_hash"),
            custom_license=frozen_custom,
        )
    reasons = sorted(
        set(list(row.get("reason_codes") or []) + ["source_license_unresolved"])
    )
    family = row.get("license_family")
    return {
        "evidence": evidence,
        "license_family": family if family in LICENSE_FAMILIES else "unknown",
        "pr_number": row.get("pr_number"),
        "primary_reason": _primary_reason(reasons),
        "reason_codes": reasons,
        "record_id": row["record_id"],
        "repo": row.get("repo") or "",
        "state": "quarantined",
    }
