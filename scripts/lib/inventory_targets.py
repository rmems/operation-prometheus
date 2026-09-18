"""Load eligibility-ledger (or simple) inventories into collector work items."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .eligibility_common import LEDGER_STATES
from .github_client import parse_repo
from .inventory_io import inventory_file_sha256, read_jsonl, resolve_inventory_path
from .source_inventory_common import sha256_json

DEFAULT_STATES = (
    "quarantined",
    "included_positive",
    "included_negative",
    "watchlist_open",
)


def _work_item(owner: str, name: str, number: int, row: dict[str, Any]) -> dict[str, Any]:
    item_id = str(row.get("item_id") or row.get("candidate_id") or "").strip()
    if not item_id:
        item_id = f"github:{owner}/{name}#{number}"
    return {
        "item_id": item_id,
        "repo": f"{owner}/{name}",
        "owner": owner,
        "pr_number": number,
        "state": row.get("state"),
        "source_state": row.get("source_state") or row.get("state"),
        "base_oid": row.get("base_oid"),
        "head_oid": row.get("head_oid"),
        "merge_commit_oid": row.get("merge_commit_oid"),
        "source_hash": row.get("source_hash") or sha256_json(row),
        "updated_at": row.get("updated_at"),
        "url": row.get("url"),
        "task_family": row.get("task_family"),
        "candidate": row,
    }


def _ledger_item_id(row: dict[str, Any], owner: str, name: str, number: int) -> str:
    candidate = str(row.get("candidate_id") or "").strip()
    if candidate:
        return candidate
    return f"github:{owner}/{name}#{number}"


def _item_from_ledger(row: dict[str, Any]) -> dict[str, Any]:
    repo = str(row.get("repository_name_with_owner") or "").strip()
    number = row.get("pull_request_number")
    if not repo:
        raise ValueError("Ledger row missing repository_name_with_owner or pull_request_number")
    if not isinstance(number, int):
        raise ValueError("Ledger row missing repository_name_with_owner or pull_request_number")
    owner, name = parse_repo(repo)
    item = _work_item(owner, name, number, row)
    item["item_id"] = _ledger_item_id(row, owner, name, number)
    item["source_state"] = row.get("source_state")
    item["source_hash"] = row.get("source_hash")
    return item


def _simple_pr_number(row: dict[str, Any], index: int) -> int:
    number = row.get("pr") if row.get("pr") is not None else row.get("pr_number")
    if number is None:
        raise ValueError(f"Simple inventory row {index} needs repo and pr")
    return int(number)


def _item_from_simple(row: dict[str, Any], index: int) -> dict[str, Any]:
    repo = str(row.get("repo") or row.get("repository_name_with_owner") or "").strip()
    if not repo:
        raise ValueError(f"Simple inventory row {index} needs repo and pr")
    number = _simple_pr_number(row, index)
    owner, name = parse_repo(repo)
    return _work_item(owner, name, number, row)


def _item_from_row(row: dict[str, Any], index: int) -> tuple[dict[str, Any], bool]:
    is_ledger = row.get("schema_version") == "eligibility_ledger_v1"
    if is_ledger:
        return _item_from_ledger(row), True
    return _item_from_simple(row, index), False


def _parse_filters(
    states: tuple[str, ...] | list[str] | None,
    owners: tuple[str, ...] | list[str] | None,
) -> tuple[set[str], set[str]]:
    state_filter = {str(s).strip() for s in (states or ()) if str(s).strip()}
    unknown = state_filter - LEDGER_STATES
    if unknown:
        raise ValueError(f"Unknown inventory states: {sorted(unknown)}")
    owner_filter = {str(o).strip().lower() for o in (owners or ()) if str(o).strip()}
    return state_filter, owner_filter


def _passes_state_filter(item: dict[str, Any], state_filter: set[str], require_state: bool) -> bool:
    if not state_filter:
        return True
    state = item.get("state")
    if require_state:
        return state in state_filter
    if not state:
        return True
    return state in state_filter


def _passes_owner_filter(item: dict[str, Any], owner_filter: set[str]) -> bool:
    if not owner_filter:
        return True
    return item["owner"].lower() in owner_filter


def _apply_limit(items: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return items
    if limit < 0:
        raise ValueError("limit must be >= 0")
    return items[:limit]


def _keep_item(
    item: dict[str, Any],
    filters: tuple[set[str], set[str]],
    seen: set[str],
    is_ledger: bool,
) -> bool:
    state_filter, owner_filter = filters
    if not _passes_state_filter(item, state_filter, is_ledger):
        return False
    if not _passes_owner_filter(item, owner_filter):
        return False
    return item["item_id"] not in seen


def _collect_items(
    rows: list[dict[str, Any]],
    filters: tuple[set[str], set[str]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        item, is_ledger = _item_from_row(row, index)
        if not _keep_item(item, filters, seen, is_ledger):
            continue
        seen.add(item["item_id"])
        items.append(item)
    items.sort(key=lambda it: (it["repo"].lower(), it["pr_number"], it["item_id"]))
    return items


def load_inventory_targets(
    path: Path,
    states: tuple[str, ...] | list[str] | None = DEFAULT_STATES,
    owners: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return (work items, inventory file sha256).

    Items are sorted by ``(repo, pr_number, item_id)`` so identical inventories
    produce identical collection order.
    """
    jsonl_path = resolve_inventory_path(path)
    digest = inventory_file_sha256(jsonl_path)
    rows = read_jsonl(jsonl_path)
    items = _collect_items(rows, _parse_filters(states, owners))
    return _apply_limit(items, limit), digest
