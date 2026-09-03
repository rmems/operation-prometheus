"""Repository rows and policy-driven repository alias resolution."""

from __future__ import annotations

from typing import Any

from .eligibility_common import REPOSITORY_SCHEMA_VERSION
from .source_inventory import sha256_json


def _repository_row(raw: dict[str, Any]) -> dict[str, Any]:
    row = {
        "schema_version": REPOSITORY_SCHEMA_VERSION,
        "provider": "github",
        "repository_id": raw.get("id"),
        "repository_database_id": raw.get("database_id"),
        "name_with_owner": raw.get("name_with_owner"),
        "owner_login": raw.get("owner_login"),
        "owner_kind": raw.get("owner_kind"),
        "name": raw.get("name"),
        "url": raw.get("url"),
        "visibility": raw.get("visibility"),
        "archived": bool(raw.get("archived")),
        "disabled": bool(raw.get("disabled")),
        "fork": bool(raw.get("fork")),
        "default_branch": raw.get("default_branch"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "pushed_at": raw.get("pushed_at"),
        "license": raw.get("license") or {},
        "pull_request_total_count": int(raw.get("pull_request_total_count") or 0),
        "aliases": [],
    }
    source_payload = {key: value for key, value in raw.items() if key != "source_hash"}
    row["source_hash"] = sha256_json(source_payload)
    return row


def _alias_fields(raw: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    return (
        str(raw.get("alias") or "").strip(),
        str(raw.get("repository_id") or "").strip(),
        str(raw.get("canonical_name_with_owner") or "").strip(),
        sorted({str(item) for item in raw.get("evidence_refs") or []}),
    )


def _alias_target(
    alias: str,
    repository_id: str,
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    repository = by_id.get(repository_id)
    if repository is None:
        raise ValueError(f"Repository alias {alias} references unknown ID {repository_id}")
    return repository


def _check_alias_canonical(alias: str, canonical: str, repository: dict[str, Any]) -> None:
    actual_canonical = str(repository["name_with_owner"])
    if canonical.casefold() != actual_canonical.casefold():
        raise ValueError(
            f"Repository alias {alias} canonical name is stale: "
            f"declared {canonical}, snapshot has {actual_canonical}"
        )


def _check_alias_collision(
    alias: str,
    repository_id: str,
    current_names: dict[str, str],
) -> None:
    current_owner = current_names.get(alias.casefold())
    if current_owner is not None and current_owner != repository_id:
        raise ValueError(f"Repository alias {alias} collides with a different current repository")


def _validated_alias(
    raw: dict[str, Any],
    seen_aliases: set[str],
    by_id: dict[str, dict[str, Any]],
    current_names: dict[str, str],
) -> tuple[str, dict[str, Any], list[str]]:
    alias, repository_id, canonical, evidence_refs = _alias_fields(raw)
    if not alias or alias.casefold() in seen_aliases:
        raise ValueError(f"Missing or duplicate repository alias {alias!r}")
    repository = _alias_target(alias, repository_id, by_id)
    _check_alias_canonical(alias, canonical, repository)
    _check_alias_collision(alias, repository_id, current_names)
    return alias, repository, evidence_refs


def _repository_indexes(
    repositories: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id = {str(row["repository_id"]): row for row in repositories}
    current_names = {
        str(row["name_with_owner"]).casefold(): str(row["repository_id"])
        for row in repositories
    }
    return by_id, current_names


def _apply_repository_aliases(
    policy: dict[str, Any],
    repositories: list[dict[str, Any]],
) -> dict[str, str]:
    by_id, current_names = _repository_indexes(repositories)
    alias_map = {name: name for name in current_names}
    seen_aliases: set[str] = set()
    for raw in policy.get("repository_aliases") or []:
        alias, repository, evidence_refs = _validated_alias(
            raw, seen_aliases, by_id, current_names
        )
        seen_aliases.add(alias.casefold())
        alias_map[alias.casefold()] = str(repository["name_with_owner"]).casefold()
        repository["aliases"].append(
            {
                "name_with_owner": alias,
                "evidence_refs": evidence_refs,
            }
        )
    for repository in repositories:
        repository["aliases"].sort(key=lambda row: row["name_with_owner"].casefold())
    return alias_map
