"""Rights-evidence checks for local-model admission."""

from __future__ import annotations

from typing import Any

from .model_admission_evidence import sha256_or_none
from .model_admission_rights import (
    classify_license_family,
    normalize_license_id,
)


def _custom_identifier_mismatch(custom: Any, rights_license: str | None) -> bool:
    if not isinstance(custom, dict):
        return False
    identifier = normalize_license_id(custom.get("identifier"))
    return identifier is not None and identifier != rights_license


def _custom_terms_mismatch(custom: Any, terms: str | None) -> bool:
    if not isinstance(custom, dict) or terms is None:
        return False
    text_digest = sha256_or_none(custom.get("text_sha256"))
    return text_digest is not None and text_digest != terms


def _declared_family(
    rights_license: str | None, custom: Any
) -> tuple[str, list[str]]:
    """Classify the rights license; unknown ids quarantine without guessing."""
    if rights_license is None:
        return "missing", ["license_missing"]
    has_custom = isinstance(custom, dict) and bool(
        sha256_or_none(custom.get("text_sha256"))
    )
    family = classify_license_family(
        rights_license, has_custom_evidence=has_custom
    )
    return family, ["license_unknown"] if family == "unknown" else []


def rights_reasons(
    candidate_license: str | None, rights_row: Any
) -> tuple[list[str], list[str], str, str | None]:
    """Return (rejected, quarantined, license_family, terms_sha256)."""
    if not isinstance(rights_row, dict):
        return [], ["rights_evidence_missing"], "missing", None

    rights_license = normalize_license_id(rights_row.get("license"))
    custom = rights_row.get("custom_license")
    terms = sha256_or_none(rights_row.get("terms_sha256"))

    rejected: list[str] = []
    quarantined: list[str] = []
    if _custom_identifier_mismatch(custom, rights_license):
        rejected.append("rights_conflict")
    family, family_reasons = _declared_family(rights_license, custom)
    quarantined += family_reasons

    if candidate_license is None:
        quarantined.append("license_missing")
    elif rights_license is not None and candidate_license != rights_license:
        rejected.append("rights_conflict")

    if terms is None:
        quarantined.append("terms_digest_missing")
    elif _custom_terms_mismatch(custom, terms):
        rejected.append("terms_digest_mismatch")
    if not (
        isinstance(rights_row.get("terms_source"), str)
        and rights_row["terms_source"].strip()
    ):
        quarantined.append("terms_source_missing")
    return rejected, quarantined, family, terms
