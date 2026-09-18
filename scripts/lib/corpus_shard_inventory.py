"""Load and index the frozen eligibility inventory for corpus merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .corpus_shard_common import (
    INVENTORY_MANIFEST_SCHEMA_VERSION,
    as_mapping,
    file_info,
    load_json_object,
    load_jsonl_objects,
    require_equal,
    require_field,
    require_text,
)


def _inventory_paths(inventory_dir: Path) -> dict[str, Path]:
    paths = {
        "manifest.json": inventory_dir / "manifest.json",
        "repositories.jsonl": inventory_dir / "repositories.jsonl",
        "candidates.jsonl": inventory_dir / "candidates.jsonl",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"Missing inventory file {missing[0]}")
    return paths


def _inventory_revision(manifest: dict[str, Any]) -> tuple[str, str]:
    require_equal(
        manifest.get("schema_version"),
        INVENTORY_MANIFEST_SCHEMA_VERSION,
        (
            "Inventory schema mismatch: expected "
            f"{INVENTORY_MANIFEST_SCHEMA_VERSION}, got {manifest.get('schema_version')!r}"
        ),
    )
    revision = require_text(
        manifest.get("snapshot_sha256"),
        "Inventory manifest is missing inventory revision (snapshot_sha256)",
    )
    policy_version = require_text(
        manifest.get("policy_version"),
        "Inventory manifest is missing policy_version",
    )
    return revision, policy_version


def _verify_inventory_digest(declared: Any, data: bytes, name: str) -> None:
    if not isinstance(declared, dict):
        return
    actual = file_info(data)
    if declared.get("sha256") != actual["sha256"]:
        raise ValueError(f"Inventory {name} digest mismatch")
    if declared.get("bytes") != actual["bytes"]:
        raise ValueError(f"Inventory {name} digest mismatch")


def _index_repositories(rows: list[dict[str, Any]]) -> list[str]:
    repository_ids = [
        require_field(row, "repository_id", label=f"repository[{index}]")
        for index, row in enumerate(rows)
    ]
    require_equal(
        len(set(repository_ids)),
        len(repository_ids),
        "Inventory repositories.jsonl contains duplicate repository_id values",
    )
    return repository_ids


def _index_candidates(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    candidate_ids: list[str] = []
    candidate_repos: dict[str, str] = {}
    for index, row in enumerate(rows):
        cid = require_field(row, "candidate_id", label=f"candidate[{index}]")
        repo_id = require_field(row, "repository_id", label=f"candidate[{index}]")
        candidate_ids.append(cid)
        candidate_repos[cid] = repo_id
    require_equal(
        len(set(candidate_ids)),
        len(candidate_ids),
        "Inventory candidates.jsonl contains duplicate candidate_id values",
    )
    return candidate_ids, candidate_repos


def load_inventory(inventory_dir: Path) -> dict[str, Any]:
    paths = _inventory_paths(inventory_dir)
    manifest = load_json_object(paths["manifest.json"])
    revision, policy_version = _inventory_revision(manifest)
    repositories_data = paths["repositories.jsonl"].read_bytes()
    candidates_data = paths["candidates.jsonl"].read_bytes()
    files = as_mapping(manifest.get("files"))
    _verify_inventory_digest(
        files.get("repositories.jsonl"), repositories_data, "repositories.jsonl"
    )
    _verify_inventory_digest(
        files.get("candidates.jsonl"), candidates_data, "candidates.jsonl"
    )
    repository_ids = _index_repositories(
        load_jsonl_objects(paths["repositories.jsonl"])
    )
    candidate_ids, candidate_repos = _index_candidates(
        load_jsonl_objects(paths["candidates.jsonl"])
    )
    return {
        "revision": revision,
        "policy_version": policy_version,
        "repository_ids": repository_ids,
        "candidate_ids": candidate_ids,
        "candidate_repos": candidate_repos,
    }
