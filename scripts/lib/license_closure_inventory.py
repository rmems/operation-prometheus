"""Inventory lookups and declaration maps for source-license closure."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .license_closure_ids import (
    LICENSE_REF_RE,
    _same_license,
    _sha256_or_none,
    _text,
    normalize_license_id,
)
from .source_inventory_common import sha256_json


def inventory_license_object(
    repository: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(repository, dict):
        return None
    license_obj = repository.get("license")
    if isinstance(license_obj, dict):
        return {
            "spdx_id": license_obj.get("spdx_id"),
            "name": license_obj.get("name"),
            "url": license_obj.get("url"),
        }
    identifier = normalize_license_id(license_obj)
    if identifier is None:
        return None
    return {"spdx_id": identifier, "name": None, "url": None}


def inventory_has_custom_evidence(repository: dict[str, Any] | None) -> bool:
    if not isinstance(repository, dict):
        return False
    custom = repository.get("custom_license")
    if not isinstance(custom, dict):
        return False
    identifier = normalize_license_id(custom.get("identifier") or custom.get("spdx_id"))
    digest = _sha256_or_none(custom.get("text_sha256") or custom.get("evidence_sha256"))
    if not identifier or not LICENSE_REF_RE.fullmatch(identifier) or not digest:
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


def record_repo(record: dict[str, Any]) -> str:
    repo = _text(record.get("repo"))
    if repo:
        return repo
    repository = record.get("repository")
    if isinstance(repository, dict):
        owner = _text(repository.get("owner"))
        name = _text(repository.get("name"))
        if owner and name:
            return f"{owner}/{name}"
    return ""


def record_id(record: dict[str, Any]) -> str:
    for key in ("id", "trajectory_id"):
        value = _text(record.get(key))
        if value:
            return value
    repo = record_repo(record)
    pr_number = record.get("pr_number")
    if repo and isinstance(pr_number, int):
        return f"{repo.replace('/', '-')}#{pr_number}"
    return repo or "unknown-record"


def record_pr_number(record: dict[str, Any]) -> int | None:
    value = record.get("pr_number")
    if isinstance(value, int) and value >= 1:
        return value
    return None


def record_license(record: dict[str, Any]) -> str | None:
    return normalize_license_id(record.get("license"))


def _folded_mapping(mapped: Any) -> dict[str, Any]:
    if not isinstance(mapped, dict):
        return {}
    return {_text(key).casefold(): value for key, value in mapped.items() if _text(key)}


def _folded_value_conflicts(mapped: Any, coerce: Callable[[Any], str | None]) -> bool:
    if not isinstance(mapped, dict):
        return False
    seen: dict[str, str | None] = {}
    for key, value in mapped.items():
        folded = _text(key).casefold()
        if not folded:
            continue
        coerced = coerce(value)
        if folded not in seen:
            seen[folded] = coerced
            continue
        previous = seen[folded]
        if previous is None or coerced is None:
            if previous != coerced:
                return True
            continue
        if previous.casefold() != coerced.casefold():
            return True
    return False


def _mapped_value(
    container: dict[str, Any],
    repo: str,
    singular: str,
    plural: str,
    coerce: Callable[[Any], str | None],
) -> str | None:
    folded = _folded_mapping(container.get(plural))
    found = coerce(folded.get(repo.casefold()))
    if found is not None:
        return found
    return coerce(container.get(singular))


def _singular_map_conflict(
    container: dict[str, Any],
    repo: str,
    singular: str,
    plural: str,
    coerce: Callable[[Any], str | None],
) -> bool:
    folded = _folded_mapping(container.get(plural))
    if repo.casefold() not in folded:
        return False
    mapped_value = coerce(folded.get(repo.casefold()))
    singular_value = coerce(container.get(singular))
    if singular_value is None:
        return False
    if mapped_value is None:
        return True
    return mapped_value.casefold() != singular_value.casefold()


def _digest_declaration_invalid(container: dict[str, Any], repo: str) -> bool:
    folded = _folded_mapping(container.get("license_evidence_digests"))
    candidates: list[Any] = []
    if repo.casefold() in folded:
        candidates.append(folded[repo.casefold()])
    if "license_evidence_digest" in container:
        candidates.append(container.get("license_evidence_digest"))
    return any(
        value is not None and _sha256_or_none(value) is None for value in candidates
    )


def _declaration_map_conflicts(
    card: dict[str, Any], manifest: dict[str, Any], repo: str
) -> bool:
    if _digest_declaration_invalid(card, repo) or _digest_declaration_invalid(
        manifest, repo
    ):
        return True
    checks = (
        (card, "source_license", "source_licenses", normalize_license_id),
        (manifest, "source_license", "source_licenses", normalize_license_id),
        (card, "license_evidence_digest", "license_evidence_digests", _sha256_or_none),
        (
            manifest,
            "license_evidence_digest",
            "license_evidence_digests",
            _sha256_or_none,
        ),
    )
    if any(
        _singular_map_conflict(container, repo, singular, plural, coerce)
        for container, singular, plural, coerce in checks
    ):
        return True
    return any(
        _folded_value_conflicts(container.get(plural), coerce)
        for container, _singular, plural, coerce in checks
    )


def _mapping_license(
    container: dict[str, Any], repo: str, singular: str, plural: str
) -> str | None:
    return _mapped_value(container, repo, singular, plural, normalize_license_id)


def _mapping_digest(
    container: dict[str, Any], repo: str, singular: str, plural: str
) -> str | None:
    return _mapped_value(container, repo, singular, plural, _sha256_or_none)


def card_license_for_repo(card: dict[str, Any], repo: str) -> str | None:
    return _mapping_license(card, repo, "source_license", "source_licenses")


def manifest_license_for_repo(manifest: dict[str, Any], repo: str) -> str | None:
    return _mapping_license(manifest, repo, "source_license", "source_licenses")


def declared_digest_for_repo(container: dict[str, Any], repo: str) -> str | None:
    return _mapping_digest(
        container,
        repo,
        "license_evidence_digest",
        "license_evidence_digests",
    )


def index_repositories(repositories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in repositories:
        name = _text(row.get("name_with_owner"))
        if not name:
            continue
        folded = name.casefold()
        if folded in index:
            raise ValueError(f"Duplicate inventory repository {name}")
        index[folded] = row
        for alias in row.get("aliases") or []:
            if isinstance(alias, dict):
                alias_name = _text(alias.get("name_with_owner")).casefold()
            else:
                alias_name = _text(alias).casefold()
            if alias_name:
                index.setdefault(alias_name, row)
    return index


def _inventory_for_repo(
    index: dict[str, dict[str, Any]],
    repo: str,
) -> dict[str, Any] | None:
    return index.get(repo.casefold()) if repo else None
