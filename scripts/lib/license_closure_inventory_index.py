"""Inventory indexing, aliases, and prior-row lookup."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import _same_license, _text, normalize_license_id
from .license_closure_inventory_license import (
    _repository_id_invalid,
    evidence_digest,
    inventory_license_object,
    license_evidence_payload,
)
from .license_closure_inventory_maps import (
    _declaration_map_conflicts,
    card_license_for_repo,
    declared_digest_for_repo,
    manifest_license_for_repo,
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
        if _repository_id_invalid(row):
            raise ValueError(
                f"repository inventory row {name} has a malformed repository_id"
            )
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


def _alias_object_invalid(alias: dict[str, Any]) -> bool:
    name = alias.get("name_with_owner")
    if not isinstance(name, str) or not name.strip():
        return True
    refs = alias.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        return True
    seen: set[str] = set()
    for item in refs:
        if not isinstance(item, str) or not item.strip():
            return True
        if item in seen:
            return True
        seen.add(item)
    return False


def _alias_name(alias: Any, name: str) -> str:
    if isinstance(alias, dict):
        if _alias_object_invalid(alias):
            alias_name = ""
        else:
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
