"""License-family and change reasons for license-closure evaluation."""

from __future__ import annotations

from .license_closure_eval_state import EvalAcc
from .license_closure_ids import (
    FORGE_LICENSE,
    LICENSE_FAMILIES,
    UNKNOWN_LICENSE_IDS,
    _same_license,
    _text,
    classify_license_family,
)
from .license_closure_pr import _markdown_discloses


def _declared_identifiers(acc: EvalAcc) -> list[str | None]:
    return [
        acc.declared_record,
        acc.declared_card,
        acc.declared_manifest,
        acc.inventory_id,
    ]


def add_family_reasons(acc: EvalAcc) -> None:
    _add_disclosure_reasons(acc)
    identifiers = _declared_identifiers(acc)
    present = [item for item in identifiers if item is not None]
    _add_missing_identifier_reasons(acc, identifiers, present)
    if present and len({item.casefold() for item in present}) > 1:
        acc.reasons.append("source_license_conflict")
        acc.reasons.append("declarations_disagree")
    _apply_closed_family(acc)
    _add_forge_reason(acc, present)
    _add_change_reasons(acc)


def _add_disclosure_reasons(acc: EvalAcc) -> None:
    if acc.declared_card is None:
        acc.reasons.append("card_disclosure_missing")
    if not _markdown_discloses(acc.markdown, acc.declared_card or acc.inventory_id):
        acc.reasons.append("card_disclosure_missing")


def _add_missing_identifier_reasons(
    acc: EvalAcc, identifiers: list[str | None], present: list[str]
) -> None:
    if not present:
        acc.reasons.append("source_license_missing")
        acc.family = "missing"
        return
    if any(item is None for item in identifiers):
        acc.reasons.append("source_license_missing")
        if acc.family not in LICENSE_FAMILIES:
            acc.family = "missing"


def _apply_closed_family(acc: EvalAcc) -> None:
    closed_family = classify_license_family(
        acc.inventory_id or acc.declared_record or acc.declared_card,
        has_custom_evidence=acc.has_custom,
    )
    if closed_family in {"missing"}:
        acc.reasons.append("source_license_missing")
        acc.family = "missing"
        return
    if closed_family == "unknown":
        acc.reasons.append("source_license_unknown")
        acc.family = "unknown"
        return
    acc.family = closed_family


def _add_forge_reason(acc: EvalAcc, present: list[str]) -> None:
    unknown_inventory = (
        acc.inventory_id is None or acc.inventory_id.upper() in UNKNOWN_LICENSE_IDS
    )
    if unknown_inventory and any(
        _text(item).casefold() == FORGE_LICENSE.casefold() for item in present
    ):
        acc.reasons.append("forge_license_substitution")


def _add_change_reasons(acc: EvalAcc) -> None:
    if any(
        check(acc)
        for check in (
            _declared_digest_changed,
            _prior_digest_changed,
            _prior_id_changed,
        )
    ):
        acc.reasons.append("source_license_changed")


def _prior_digest_changed(acc: EvalAcc) -> bool:
    if acc.prior_digest is None or acc.digest is None:
        return False
    return acc.prior_digest != acc.digest


def _declared_digest_changed(acc: EvalAcc) -> bool:
    if acc.digest is None:
        return False
    return any(
        declared is not None and declared != acc.digest
        for declared in (acc.card_digest, acc.manifest_digest)
    )


def _prior_id_changed(acc: EvalAcc) -> bool:
    if acc.prior_id is None or acc.inventory_id is None:
        return False
    return not _same_license(acc.prior_id, acc.inventory_id)



