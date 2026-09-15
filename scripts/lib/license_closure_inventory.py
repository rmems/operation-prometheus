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


def inventory_has_custom_evidence(repository: dict[str, Any] | None) -> bool:
    if not isinstance(repository, dict):
        return False
    custom = repository.get("custom_license")
    if not isinstance(custom, dict):
        return False
    identifier = _custom_license_identifier(custom)
    digest = _custom_license_digest(custom)
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


def _authenticated_inventory_source_hash(
    repository: dict[str, Any] | None,
) -> str | None:
    """Return the row hash only when visibility is public and the digest matches."""
    if not isinstance(repository, dict):
        return None
    if repository.get("visibility") != "public":
        return None
    declared = _sha256_or_none(repository.get("source_hash"))
    if declared is None or declared != inventory_row_source_hash(repository):
        return None
    return declared


def source_provenance_digest(
    repo: str,
    repository_source_hash: str,
    snapshot_sha256: str,
    *,
    record_id: str = "",
    pr_number: int | None = None,
    evidence_digest: str = "",
) -> str:
    """Bind a released row to its trajectory, license evidence, repository, and snapshot."""
    return sha256_json(
        {
            "evidence_digest": evidence_digest,
            "pr_number": pr_number,
            "record_id": record_id,
            "repo": repo,
            "repository_source_hash": repository_source_hash,
            "snapshot_sha256": snapshot_sha256,
        }
    )


def _nested_record_repo(record: dict[str, Any]) -> str:
    repository = record.get("repository")
    if isinstance(repository, dict):
        owner = _text(repository.get("owner"))
        name = _text(repository.get("name"))
        if owner and name:
            return f"{owner}/{name}"
    return ""


def record_repo(record: dict[str, Any]) -> str:
    return _text(record.get("repo")) or _nested_record_repo(record)


def record_repo_identities_conflict(record: dict[str, Any]) -> bool:
    top = _text(record.get("repo"))
    nested = _nested_record_repo(record)
    return bool(top and nested and top.casefold() != nested.casefold())


def _supplied_record_id(record: dict[str, Any]) -> str:
    for key in ("id", "trajectory_id"):
        value = _text(record.get(key))
        if value:
            return value
    return ""


def record_ids_conflict(record: dict[str, Any]) -> bool:
    record_key = _text(record.get("id"))
    trajectory_key = _text(record.get("trajectory_id"))
    return bool(record_key and trajectory_key and record_key != trajectory_key)


def record_id(record: dict[str, Any]) -> str:
    supplied = _supplied_record_id(record)
    if supplied:
        return supplied
    repo = record_repo(record)
    pr_number = record.get("pr_number")
    if repo and type(pr_number) is int and pr_number >= 1:
        return f"{repo.replace('/', '-')}#{pr_number}"
    return repo or "unknown-record"


def record_pr_number(record: dict[str, Any]) -> int | None:
    value = record.get("pr_number")
    if type(value) is int and value >= 1:
        return value
    return None


def record_pr_number_invalid(record: dict[str, Any]) -> bool:
    if "pr_number" not in record:
        return False
    value = record["pr_number"]
    if value is None:
        return False
    return not (type(value) is int and value >= 1)


def record_license(record: dict[str, Any]) -> str | None:
    value = record.get("license")
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _folded_mapping(mapped: Any) -> dict[str, Any]:
    if not isinstance(mapped, dict):
        return {}
    return {_text(key).casefold(): value for key, value in mapped.items() if _text(key)}


def _malformed_plural_field(container: dict[str, Any], plural: str) -> bool:
    if plural not in container:
        return False
    return not isinstance(container.get(plural), dict)


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


def _mapped_value_for_names(
    container: dict[str, Any],
    names: list[str],
    singular: str,
    plural: str,
    coerce: Callable[[Any], str | None],
) -> str | None:
    folded = _folded_mapping(container.get(plural))
    for name in names:
        if not name or name.casefold() not in folded:
            continue
        found = coerce(folded.get(name.casefold()))
        if found is not None:
            return found
    return coerce(container.get(singular))


def _alias_group_value_conflicts(
    mapped: Any,
    names: list[str],
    coerce: Callable[[Any], str | None],
) -> bool:
    if not isinstance(mapped, dict):
        return False
    folded = _folded_mapping(mapped)
    seen: list[str | None] = []
    for name in names:
        if not name or name.casefold() not in folded:
            continue
        coerced = coerce(folded[name.casefold()])
        seen.append(None if coerced is None else coerced.casefold())
    return len(set(seen)) > 1


def _malformed_present_value(
    container: dict[str, Any],
    key: str,
    coerce: Callable[[Any], str | None],
) -> bool:
    if key not in container:
        return False
    value = container.get(key)
    if value is None:
        return False
    return coerce(value) is None


def _singular_map_conflict(
    container: dict[str, Any],
    repo: str,
    singular: str,
    plural: str,
    coerce: Callable[[Any], str | None],
) -> bool:
    if _malformed_present_value(container, singular, coerce):
        return True
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
    card: dict[str, Any], manifest: dict[str, Any], names: list[str]
) -> bool:
    repos = [name for name in names if name] or [""]
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
        _digest_declaration_invalid(container, repo)
        for container in (card, manifest)
        for repo in repos
    ):
        return True
    if any(
        _malformed_plural_field(container, plural)
        for container, _singular, plural, _coerce in checks
    ):
        return True
    if any(
        _singular_map_conflict(container, repo, singular, plural, coerce)
        for container, singular, plural, coerce in checks
        for repo in repos
    ):
        return True
    if any(
        _folded_value_conflicts(container.get(plural), coerce)
        for container, _singular, plural, coerce in checks
    ):
        return True
    return any(
        _alias_group_value_conflicts(container.get(plural), repos, coerce)
        for container, _singular, plural, coerce in checks
    )


def _declared_source_maps_conflict(
    card: dict[str, Any],
    manifest: dict[str, Any],
    declared_repos: set[str],
    inventory_index: dict[str, dict[str, Any]],
) -> bool:
    for name in declared_repos:
        inventory = _inventory_for_repo(inventory_index, name)
        names = _identity_names(inventory, name)
        if _declaration_map_conflicts(card, manifest, names):
            return True
        card_license = card_license_for_repo(card, names)
        manifest_license = manifest_license_for_repo(manifest, names)
        if card_license is None or manifest_license is None:
            return True
        if not _same_license(card_license, manifest_license):
            return True
        inventory_license = normalize_license_id(inventory_license_object(inventory))
        if card_license is not None and not _same_license(
            card_license, inventory_license
        ):
            return True
        if manifest_license is not None and not _same_license(
            manifest_license, inventory_license
        ):
            return True
        card_digest = declared_digest_for_repo(card, names)
        manifest_digest = declared_digest_for_repo(manifest, names)
        if (
            card_digest is not None
            and manifest_digest is not None
            and card_digest != manifest_digest
        ):
            return True
        inventory_digest = (
            evidence_digest(license_evidence_payload(inventory))
            if isinstance(inventory, dict)
            else None
        )
        if card_digest is not None and card_digest != inventory_digest:
            return True
        if manifest_digest is not None and manifest_digest != inventory_digest:
            return True
    return False


def _mapping_license(
    container: dict[str, Any], names: list[str], singular: str, plural: str
) -> str | None:
    return _mapped_value_for_names(
        container, names, singular, plural, normalize_license_id
    )


def _mapping_digest(
    container: dict[str, Any], names: list[str], singular: str, plural: str
) -> str | None:
    return _mapped_value_for_names(container, names, singular, plural, _sha256_or_none)


def card_license_for_repo(card: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_license(card, names, "source_license", "source_licenses")


def manifest_license_for_repo(manifest: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_license(manifest, names, "source_license", "source_licenses")


def declared_digest_for_repo(container: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_digest(
        container,
        names,
        "license_evidence_digest",
        "license_evidence_digests",
    )


def index_repositories(repositories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    seen_ids: dict[str, str] = {}
    for row in repositories:
        if not isinstance(row, dict):
            raise ValueError("repository inventory rows must be objects")
        name = _text(row.get("name_with_owner"))
        if not name:
            raise ValueError("repository inventory row is missing a canonical name")
        folded = name.casefold()
        if folded in index:
            raise ValueError(f"Duplicate inventory repository {name}")
        repo_id = _text(row.get("repository_id"))
        if repo_id:
            previous = seen_ids.get(repo_id)
            if previous is not None and previous != folded:
                raise ValueError(f"Duplicate inventory repository id {repo_id}")
            seen_ids[repo_id] = folded
        index[folded] = row
        for alias in _alias_entries(row, name):
            alias_name = _alias_name(alias, name).casefold()
            existing = index.get(alias_name)
            if existing is not None and existing is not row:
                raise ValueError(f"Duplicate inventory alias {alias_name}")
            index[alias_name] = row
    return index


def _inventory_for_repo(
    index: dict[str, dict[str, Any]],
    repo: str,
) -> dict[str, Any] | None:
    return index.get(repo.casefold()) if repo else None


def _alias_entries(row: dict[str, Any], name: str) -> list[Any]:
    aliases = row.get("aliases")
    if aliases is None:
        return []
    if not isinstance(aliases, list):
        raise ValueError(f"inventory aliases for {name} must be an array")
    return aliases


def _alias_name(alias: Any, name: str) -> str:
    if isinstance(alias, dict):
        alias_name = _text(alias.get("name_with_owner"))
    elif isinstance(alias, str):
        alias_name = alias.strip()
    else:
        alias_name = ""
    if not alias_name:
        raise ValueError(f"inventory aliases for {name} contain a malformed entry")
    return alias_name


def _repository_names(row: dict[str, Any]) -> list[str]:
    names = [_text(row.get("name_with_owner"))]
    canonical = names[0] if names else ""
    names.extend(
        _alias_name(alias, canonical) for alias in _alias_entries(row, canonical)
    )
    return [name for name in names if name]


def _canonical_declared_repos(
    names: set[str],
    inventory_index: dict[str, dict[str, Any]],
) -> set[str]:
    keys: set[str] = set()
    for name in names:
        folded = name.casefold()
        row = inventory_index.get(folded)
        if isinstance(row, dict):
            repo_id = _text(row.get("repository_id"))
            if repo_id:
                keys.add(f"id:{repo_id}")
                continue
            canonical = _text(row.get("name_with_owner")).casefold()
            if canonical:
                keys.add(f"name:{canonical}")
                continue
        keys.add(f"name:{folded}")
    return keys


def _identity_names(repository: dict[str, Any] | None, repo: str) -> list[str]:
    names = [repo] if repo else []
    if isinstance(repository, dict):
        names.extend(_repository_names(repository))
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        folded = name.casefold()
        if not name or folded in seen:
            continue
        seen.add(folded)
        unique.append(name)
    return unique


def _unique_inventory_rows(index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in index.values():
        ident = id(row)
        if ident in seen:
            continue
        seen.add(ident)
        rows.append(row)
    return rows


def _prior_repository(
    prior_index: dict[str, dict[str, Any]],
    current: dict[str, Any] | None,
    repo: str,
) -> dict[str, Any] | None:
    if isinstance(current, dict):
        repo_id = _text(current.get("repository_id"))
        if repo_id:
            for row in _unique_inventory_rows(prior_index):
                if _text(row.get("repository_id")) == repo_id:
                    return row
            return None
    found = _inventory_for_repo(prior_index, repo)
    if found is not None or not isinstance(current, dict):
        return found
    for name in _repository_names(current):
        found = _inventory_for_repo(prior_index, name)
        if found is not None:
            return found
    return None
