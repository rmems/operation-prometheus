"""Load eligibility-ledger (or simple) inventories into collector work items."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .eligibility_common import LEDGER_STATES
from .github_client import parse_repo
from .source_inventory_common import sha256_json

DEFAULT_STATES = (
    "quarantined",
    "included_positive",
    "included_negative",
    "watchlist_open",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{lineno} is not a JSON object")
        rows.append(row)
    return rows


def resolve_inventory_path(path: Path) -> Path:
    """Accept a candidates JSONL file or a ledger directory containing one."""
    path = Path(path)
    if path.is_dir():
        candidate = path / "candidates.jsonl"
        if not candidate.is_file():
            raise FileNotFoundError(f"No candidates.jsonl in inventory directory {path}")
        return candidate
    if not path.is_file():
        raise FileNotFoundError(f"Inventory not found: {path}")
    return path


def inventory_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _item_from_ledger(row: dict[str, Any]) -> dict[str, Any]:
    repo = str(row.get("repository_name_with_owner") or "").strip()
    number = row.get("pull_request_number")
    if not repo or not isinstance(number, int):
        raise ValueError("Ledger row missing repository_name_with_owner or pull_request_number")
    owner, name = parse_repo(repo)
    candidate_id = str(row.get("candidate_id") or "").strip()
    if not candidate_id:
        candidate_id = f"github:{owner}/{name}#{number}"
    return {
        "item_id": candidate_id,
        "repo": f"{owner}/{name}",
        "owner": owner,
        "pr_number": number,
        "state": row.get("state"),
        "source_state": row.get("source_state"),
        "base_oid": row.get("base_oid"),
        "head_oid": row.get("head_oid"),
        "merge_commit_oid": row.get("merge_commit_oid"),
        "source_hash": row.get("source_hash"),
        "updated_at": row.get("updated_at"),
        "url": row.get("url"),
        "task_family": row.get("task_family"),
        "candidate": row,
    }


def _item_from_simple(row: dict[str, Any], index: int) -> dict[str, Any]:
    repo = str(row.get("repo") or row.get("repository_name_with_owner") or "").strip()
    number = row.get("pr") if row.get("pr") is not None else row.get("pr_number")
    if not repo or number is None:
        raise ValueError(f"Simple inventory row {index} needs repo and pr")
    number = int(number)
    owner, name = parse_repo(repo)
    item_id = str(row.get("item_id") or row.get("candidate_id") or f"github:{owner}/{name}#{number}")
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


def load_inventory_targets(
    path: Path,
    *,
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
    rows = _read_jsonl(jsonl_path)
    state_filter = {str(s).strip() for s in (states or ()) if str(s).strip()}
    unknown = state_filter - LEDGER_STATES
    if unknown:
        raise ValueError(f"Unknown inventory states: {sorted(unknown)}")
    owner_filter = {str(o).strip().lower() for o in (owners or ()) if str(o).strip()}

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        schema = row.get("schema_version")
        if schema == "eligibility_ledger_v1":
            item = _item_from_ledger(row)
            if state_filter and item.get("state") not in state_filter:
                continue
        else:
            item = _item_from_simple(row, index)
            if state_filter and item.get("state") and item["state"] not in state_filter:
                continue
        if owner_filter and item["owner"].lower() not in owner_filter:
            continue
        if item["item_id"] in seen:
            continue
        seen.add(item["item_id"])
        items.append(item)

    items.sort(key=lambda it: (it["repo"].lower(), it["pr_number"], it["item_id"]))
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        items = items[:limit]
    return items, digest
