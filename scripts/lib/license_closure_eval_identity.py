"""Identity and inventory lookup for license-closure evaluation."""

from __future__ import annotations

from .license_closure_eval_state import EvalAcc
from .license_closure_ids import classify_license_family, normalize_license_id
from .license_closure_inventory import (
    _identity_names,
    _inventory_for_repo,
    _supplied_record_id,
    card_license_for_repo,
    inventory_has_custom_evidence,
    inventory_license_object,
    manifest_license_for_repo,
    record_id,
    record_ids_conflict,
    record_license,
    record_pr_number,
    record_pr_number_invalid,
    record_repo,
    record_repo_identities_conflict,
)


def add_identity_reasons(acc: EvalAcc) -> None:
    acc.repo = record_repo(acc.record)
    if record_repo_identities_conflict(acc.record):
        acc.reasons.append("declarations_disagree")
    acc.rid = record_id(acc.record)
    if not _supplied_record_id(acc.record):
        acc.reasons.append("declarations_disagree")
    if record_ids_conflict(acc.record):
        acc.reasons.append("declarations_disagree")
    acc.pr_number = record_pr_number(acc.record)
    if record_pr_number_invalid(acc.record):
        acc.reasons.append("declarations_disagree")


def load_license_state(acc: EvalAcc) -> None:
    acc.declared_record = record_license(acc.record)
    acc.repository = _inventory_for_repo(acc.inventory_index, acc.repo)
    acc.names = _identity_names(acc.repository, acc.repo)
    acc.declared_card = card_license_for_repo(acc.card, acc.names)
    acc.declared_manifest = manifest_license_for_repo(acc.manifest, acc.names)
    acc.inventory_license = inventory_license_object(acc.repository)
    acc.inventory_id = normalize_license_id(acc.inventory_license)
    acc.has_custom = inventory_has_custom_evidence(acc.repository)
    _load_custom_license(acc)
    acc.family = classify_license_family(
        acc.inventory_id, has_custom_evidence=acc.has_custom
    )
    if acc.family == "missing":
        acc.family = classify_license_family(
            acc.declared_record, has_custom_evidence=acc.has_custom
        )


def _load_custom_license(acc: EvalAcc) -> None:
    if not isinstance(acc.repository, dict):
        return
    custom = acc.repository.get("custom_license")
    if not isinstance(custom, dict):
        return
    acc.custom_license_obj = custom
    if not acc.has_custom:
        acc.reasons.append("source_license_conflict")
