"""Deterministic merge of Operation Prometheus corpus shards.

Shard extractors (#56/#57/#58) own record bytes. This facade verifies
assignment, inventory coverage, and manifests, then concatenates those
bytes into one canonical global JSONL plus a digest-pinned manifest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .corpus_shard_common import (
    ASSIGNMENT_RULE,
    GLOBAL_MANIFEST_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    SHARD_COUNT,
    SHARD_MANIFEST_SCHEMA_VERSION,
    STATE_COUNT_FIELDS,
    TRAJECTORY_SCHEMA_VERSION,
    LoadedShard,
    assign_shard,
    digest_manifest,
    empty_state_counts,
    file_info,
    require_locked_shard_count,
)
from .corpus_shard_inventory import load_inventory
from .corpus_shard_verify import (
    Coverage,
    discover_shard_dirs,
    load_shard,
    repos_by_shard,
    verify_shard_members,
)
from .eligibility_render import render_json

__all__ = [
    "ASSIGNMENT_RULE",
    "RECORD_SCHEMA_VERSION",
    "SHARD_COUNT",
    "SHARD_MANIFEST_SCHEMA_VERSION",
    "STATE_COUNT_FIELDS",
    "TRAJECTORY_SCHEMA_VERSION",
    "assign_shard",
    "digest_manifest",
    "merge_corpus_shards",
]


def merge_corpus_shards(
    inventory_dir: Path,
    shards_dir: Path,
    *,
    shard_count: int = SHARD_COUNT,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Verify shards against the frozen inventory and emit global artifacts."""
    require_locked_shard_count(shard_count)
    inventory = load_inventory(inventory_dir)
    coverage = Coverage(
        inventory=inventory,
        expected_repos=repos_by_shard(inventory, shard_count),
        seen_repositories={},
        seen_candidates={},
        shard_count=shard_count,
    )
    shards = _load_shards(shards_dir, coverage)
    record_lines = _collect_preserved(shards, coverage)
    return _render_global(inventory, shards, record_lines)


def _load_shards(shards_dir: Path, coverage: Coverage) -> list[LoadedShard]:
    shard_dirs = discover_shard_dirs(shards_dir, coverage.shard_count)
    return [
        load_shard(shard_dirs[number], number, coverage)
        for number in range(coverage.shard_count)
    ]


def _collect_preserved(shards: list[LoadedShard], coverage: Coverage) -> list[bytes]:
    preserved: list[tuple[bytes, str]] = []
    for shard in shards:
        preserved.extend(verify_shard_members(shard, coverage))
    uncovered = [
        cid
        for cid in coverage.inventory["candidate_ids"]
        if cid not in coverage.seen_candidates
    ]
    if uncovered:
        raise ValueError(f"Unaccounted inventory row {uncovered[0]}")
    preserved.sort(key=lambda item: item[1])
    return [raw for raw, _candidate_id in preserved]


def _global_counts(
    inventory: dict[str, Any], shards: list[LoadedShard], record_count: int
) -> dict[str, int]:
    state_counts = empty_state_counts()
    for shard in shards:
        for field in STATE_COUNT_FIELDS:
            state_counts[field] += int(shard.manifest["counts"][field])
    return {
        "repository_count": len(inventory["repository_ids"]),
        "record_count": record_count,
        **state_counts,
    }


def _shard_summary(shard: LoadedShard) -> dict[str, Any]:
    counts = shard.manifest["counts"]
    records_info = shard.manifest["files"]["records.jsonl"]
    return {
        "shard_number": shard.number,
        "manifest_sha256": shard.manifest["manifest_sha256"],
        "records_sha256": records_info["sha256"],
        "records_bytes": records_info["bytes"],
        "repository_count": counts["repository_count"],
        "record_count": counts["record_count"],
        "counts": {
            "repository_count": counts["repository_count"],
            "record_count": counts["record_count"],
            **{field: counts[field] for field in STATE_COUNT_FIELDS},
        },
    }


def _render_global(
    inventory: dict[str, Any],
    shards: list[LoadedShard],
    record_lines: list[bytes],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    records_bytes = b"".join(line + b"\n" for line in record_lines)
    counts = _global_counts(inventory, shards, len(record_lines))
    manifest: dict[str, Any] = {
        "schema_version": GLOBAL_MANIFEST_SCHEMA_VERSION,
        "provider": "github",
        "shard_count": len(shards),
        "assignment_rule": ASSIGNMENT_RULE,
        "inventory_revision": inventory["revision"],
        "inventory_policy_version": inventory["policy_version"],
        "trajectory_schema_version": TRAJECTORY_SCHEMA_VERSION,
        "counts": counts,
        "exclusion_total": counts["excluded"],
        "quarantine_total": counts["quarantined"],
        "shards": [_shard_summary(shard) for shard in shards],
        "files": {"records.jsonl": file_info(records_bytes)},
    }
    manifest["manifest_sha256"] = digest_manifest(manifest)
    rendered = {
        "records.jsonl": records_bytes,
        "manifest.json": render_json(manifest),
    }
    return manifest, rendered
