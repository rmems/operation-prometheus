"""License objects, custom evidence, and inventory hashes."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import (
    LICENSE_REF_RE,
    _same_license,
    _sha256_or_none,
    normalize_license_id,
)
from .source_inventory_common import sha256_json


def inventory_license_object(
    repository: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(repository, dict):
        return None
    license_obj = repository.get("license")
    if not isinstance(license_obj, dict):
        return None
    return {
        "spdx_id": license_obj.get("spdx_id"),
        "name": license_obj.get("name"),
        "url": license_obj.get("url"),
    }


def _custom_license_identifier(custom: dict[str, Any]) -> str | None:
    from_identifier = normalize_license_id(custom.get("identifier"))
    from_spdx = normalize_license_id(custom.get("spdx_id"))
    if "identifier" in custom and "spdx_id" in custom:
        if from_identifier is None or from_spdx is None:
            return None
        if not _same_license(from_identifier, from_spdx):
            return None
    return from_identifier or from_spdx


def _custom_license_digest(custom: dict[str, Any]) -> str | None:
    from_text = _sha256_or_none(custom.get("text_sha256"))
    from_evidence = _sha256_or_none(custom.get("evidence_sha256"))
    if "text_sha256" in custom and "evidence_sha256" in custom:
        if from_text is None or from_evidence is None:
            return None
        if from_text != from_evidence:
            return None
    return from_text or from_evidence


def _custom_evidence_identifier(custom: dict[str, Any]) -> str | None:
    identifier = _custom_license_identifier(custom)
    if not identifier or not LICENSE_REF_RE.fullmatch(identifier):
        return None
    if not _custom_license_digest(custom):
        return None
    return identifier


def inventory_has_custom_evidence(repository: dict[str, Any] | None) -> bool:
    if not isinstance(repository, dict):
        return False
    custom = repository.get("custom_license")
    if not isinstance(custom, dict):
        return False
    identifier = _custom_evidence_identifier(custom)
    if identifier is None:
        return False
    inventory_id = normalize_license_id(inventory_license_object(repository))
    return _same_license(identifier, inventory_id)


def license_evidence_payload(repository: dict[str, Any]) -> dict[str, Any]:
    license_obj = inventory_license_object(repository) or {
        "spdx_id": None,
        "name": None,
        "url": None,
    }
    custom = (
        repository.get("custom_license")
        if isinstance(repository.get("custom_license"), dict)
        else None
    )
    return {
        "custom_license": custom,
        "license": license_obj,
    }


def evidence_digest(payload: dict[str, Any]) -> str:
    return sha256_json(payload)


def inventory_row_source_hash(repository: dict[str, Any]) -> str:
    """Hash the eligibility producer payload, not the published wrapper fields.

    ``eligibility_repositories._repository_row`` hashes the incoming GitHub
    source object before renaming ids and adding aliases. Reconstruct that
    payload so frozen v0.7 inventory rows authenticate, while a tampered
    license object still fails the digest.
    """
    return sha256_json(
        {
            "archived": bool(repository.get("archived")),
            "created_at": repository.get("created_at"),
            "database_id": repository.get("repository_database_id"),
            "default_branch": repository.get("default_branch"),
            "disabled": bool(repository.get("disabled")),
            "fork": bool(repository.get("fork")),
            "id": repository.get("repository_id"),
            "license": repository.get("license") or {},
            "name": repository.get("name"),
            "name_with_owner": repository.get("name_with_owner"),
            "owner_kind": repository.get("owner_kind"),
            "owner_login": repository.get("owner_login"),
            "pull_request_total_count": int(
                repository.get("pull_request_total_count") or 0
            ),
            "pushed_at": repository.get("pushed_at"),
            "updated_at": repository.get("updated_at"),
            "url": repository.get("url"),
            "visibility": repository.get("visibility"),
        }
    )


_PRODUCER_BOOL_KEYS = ("archived", "disabled", "fork")


def _producer_scalars_invalid(repository: dict[str, Any]) -> bool:
    if any(
        key in repository and type(repository[key]) is not bool
        for key in _PRODUCER_BOOL_KEYS
    ):
        return True
    if "pull_request_total_count" not in repository:
        return False
    return type(repository["pull_request_total_count"]) is not int


def _repository_id_invalid(row: dict[str, Any]) -> bool:
    if "repository_id" not in row:
        return False
    value = row["repository_id"]
    return not isinstance(value, str) or not value.strip()


def _declared_license_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _authenticated_inventory_source_hash(
    repository: dict[str, Any] | None,
) -> str | None:
    """Return the row hash only when visibility is public and the digest matches."""
    if not isinstance(repository, dict):
        return None
    if repository.get("visibility") != "public":
        return None
    if _producer_scalars_invalid(repository) or _repository_id_invalid(repository):
        return None
    declared = _sha256_or_none(repository.get("source_hash"))
    if declared is None or declared != inventory_row_source_hash(repository):
        return None
    return declared


def source_provenance_digest(
    repo: str,
    repository_source_hash: str,
    snapshot_sha256: str,
    binding: dict[str, Any] | None = None,
) -> str:
    """Bind a released row to its trajectory, license evidence, repository, and snapshot."""
    binding = binding or {}
    return sha256_json(
        {
            "evidence_digest": binding.get("evidence_digest", ""),
            "pr_number": binding.get("pr_number"),
            "record_id": binding.get("record_id", ""),
            "repo": repo,
            "repository_source_hash": repository_source_hash,
            "snapshot_sha256": snapshot_sha256,
        }
    )
