"""Repository identity diffs for the weekly source-inventory audit."""

from __future__ import annotations

from typing import Any


def keep(values: list[Any]) -> list[Any]:
    rows: list[Any] = []
    for item in values:
        if item is not None:
            rows.append(item)
    return rows


def repo_key(row: dict[str, Any]) -> str:
    repo_id = row.get("repository_id")
    if repo_id:
        return str(repo_id)
    ident = row.get("id")
    if ident:
        return str(ident)
    return ""


def repo_name(row: dict[str, Any]) -> str:
    named = row.get("name_with_owner")
    if named:
        return str(named)
    alt = row.get("repository_name_with_owner")
    if alt:
        return str(alt)
    return ""


def _index_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {repo_key(row): row for row in rows if repo_key(row)}


def _index_by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {repo_name(row).casefold(): row for row in rows if repo_name(row)}


def _named(row: dict[str, Any], repo_id: str) -> dict[str, str]:
    return {"repository_id": repo_id, "name_with_owner": repo_name(row)}


def _peer_is_same(peer: dict[str, Any] | None, repo_id: str) -> bool:
    if peer is None:
        return False
    return repo_key(peer) == repo_id


def _id_only_row(
    repo_id: str,
    row: dict[str, Any],
    other_by_id: dict[str, dict[str, Any]],
    other_by_name: dict[str, dict[str, Any]],
) -> dict[str, str] | None:
    if repo_id in other_by_id:
        return None
    peer = other_by_name.get(repo_name(row).casefold())
    if _peer_is_same(peer, repo_id):
        return None
    return _named(row, repo_id)


def _id_only_in(
    primary_by_id: dict[str, dict[str, Any]],
    other_by_id: dict[str, dict[str, Any]],
    other_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    return keep(
        [
            _id_only_row(repo_id, row, other_by_id, other_by_name)
            for repo_id, row in primary_by_id.items()
        ]
    )


def _rename_payload(repo_id: str, frozen_name: str, live_name: str) -> dict[str, str]:
    return {"repository_id": repo_id, "from": frozen_name, "to": live_name}


def _rename_if_changed(
    repo_id: str, frozen_name: str, live_name: str
) -> dict[str, str] | None:
    if frozen_name.casefold() == live_name.casefold():
        return None
    return _rename_payload(repo_id, frozen_name, live_name)


def _one_rename(
    repo_id: str, frozen_row: dict[str, Any], live_row: dict[str, Any] | None
) -> dict[str, str] | None:
    if live_row is None:
        return None
    frozen_name = repo_name(frozen_row)
    live_name = repo_name(live_row)
    if not frozen_name:
        return None
    if not live_name:
        return None
    return _rename_if_changed(repo_id, frozen_name, live_name)


def _renamed_repositories(
    frozen_by_id: dict[str, dict[str, Any]],
    live_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    return keep(
        [
            _one_rename(repo_id, frozen_row, live_by_id.get(repo_id))
            for repo_id, frozen_row in frozen_by_id.items()
        ]
    )


def diff_repositories(
    frozen: list[dict[str, Any]],
    live: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    frozen_by_id = _index_by_id(frozen)
    live_by_id = _index_by_id(live)
    frozen_by_name = _index_by_name(frozen)
    live_by_name = _index_by_name(live)
    return {
        "new": _id_only_in(live_by_id, frozen_by_id, frozen_by_name),
        "deleted": _id_only_in(frozen_by_id, live_by_id, live_by_name),
        "renamed": _renamed_repositories(frozen_by_id, live_by_id),
    }
