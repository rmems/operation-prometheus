"""Builders for corpus-shard merge tests (Linear RM-1345 / GH #53)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lib.corpus_shards import (
    ASSIGNMENT_RULE,
    RECORD_SCHEMA_VERSION,
    SHARD_COUNT,
    SHARD_MANIFEST_SCHEMA_VERSION,
    STATE_COUNT_FIELDS,
    TRAJECTORY_SCHEMA_VERSION,
    assign_shard,
    digest_manifest,
)
from lib.eligibility_render import render_json
from lib.source_inventory_common import sha256_json

INVENTORY_POLICY_VERSION = "v0.7-eligibility.1"
REPOSITORY_IDS = {
    0: "R_test_4",
    1: "R_test_0",
    2: "R_test_2",
}
REPOSITORY_NAMES = {
    0: "rmems/repo-shard-0",
    1: "rmems/repo-shard-1",
    2: "rmems/repo-shard-2",
}


def _file_info(data: bytes) -> dict[str, int | str]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _state_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in STATE_COUNT_FIELDS}
    for row in records:
        counts[str(row["state"])] += 1
    return counts


def _record(spec: dict[str, Any]) -> bytes:
    candidate_id = spec["candidate_id"]
    repository_id = spec["repository_id"]
    state = spec["state"]
    reason = spec["reason"]
    payload = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "repository_id": repository_id,
        "state": state,
        "reason_codes": [reason],
    }
    if spec.get("canonical", True):
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    # Non-canonical on purpose: spaces and insertion order must survive the merge.
    ordered = {
        "state": state,
        "reason_codes": [reason],
        "candidate_id": candidate_id,
        "repository_id": repository_id,
        "schema_version": RECORD_SCHEMA_VERSION,
    }
    return json.dumps(ordered, ensure_ascii=False).encode("utf-8")


def valid_records() -> dict[int, list[bytes]]:
    return {
        0: [
            _record(
                {
                    "candidate_id": "github:repository:R_test_4:pull:PR_a",
                    "repository_id": REPOSITORY_IDS[0],
                    "state": "included_positive",
                    "reason": "explicit_override",
                    "canonical": False,
                }
            ),
            _record(
                {
                    "candidate_id": "github:repository:R_test_4:pull:PR_z",
                    "repository_id": REPOSITORY_IDS[0],
                    "state": "excluded",
                    "reason": "dependency_only",
                }
            ),
        ],
        1: [
            _record(
                {
                    "candidate_id": "github:repository:R_test_0:pull:PR_m",
                    "repository_id": REPOSITORY_IDS[1],
                    "state": "quarantined",
                    "reason": "missing_code_state",
                }
            ),
            _record(
                {
                    "candidate_id": "github:repository:R_test_0:pull:PR_w",
                    "repository_id": REPOSITORY_IDS[1],
                    "state": "watchlist_open",
                    "reason": "mutable_open_work",
                }
            ),
        ],
        2: [
            _record(
                {
                    "candidate_id": "github:repository:R_test_2:pull:PR_n",
                    "repository_id": REPOSITORY_IDS[2],
                    "state": "included_negative",
                    "reason": "explicit_negative_override",
                }
            ),
        ],
    }


def _candidate_row(raw: bytes) -> dict[str, str]:
    record = json.loads(raw.decode("utf-8"))
    return {
        "candidate_id": record["candidate_id"],
        "repository_id": record["repository_id"],
        "state": record["state"],
    }


def _repository_row(repository_id: str, name: str) -> dict[str, str]:
    return {"repository_id": repository_id, "name_with_owner": name}


def write_jsonl(path: Path, lines: list[bytes]) -> bytes:
    data = b"".join(line + b"\n" for line in lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def write_inventory(
    path: Path, records_by_shard: dict[int, list[bytes]] | None = None
) -> dict[str, Any]:
    records_by_shard = (
        records_by_shard if records_by_shard is not None else valid_records()
    )
    repositories = [
        _repository_row(REPOSITORY_IDS[number], REPOSITORY_NAMES[number])
        for number in range(SHARD_COUNT)
    ]
    candidates = [
        _candidate_row(raw)
        for number in range(SHARD_COUNT)
        for raw in records_by_shard[number]
    ]
    repo_lines = [
        json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        for row in repositories
    ]
    candidate_lines = [
        json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        for row in candidates
    ]
    path.mkdir(parents=True, exist_ok=True)
    repositories_bytes = write_jsonl(path / "repositories.jsonl", repo_lines)
    candidates_bytes = write_jsonl(path / "candidates.jsonl", candidate_lines)
    revision = sha256_json(
        {
            "fixture": "corpus-shard-merge-v0.7",
            "repository_ids": [row["repository_id"] for row in repositories],
            "candidate_ids": [row["candidate_id"] for row in candidates],
        }
    )
    manifest = {
        "schema_version": "eligibility_manifest_v1",
        "snapshot_sha256": revision,
        "policy_version": INVENTORY_POLICY_VERSION,
        "files": {
            "repositories.jsonl": _file_info(repositories_bytes),
            "candidates.jsonl": _file_info(candidates_bytes),
        },
    }
    (path / "manifest.json").write_bytes(render_json(manifest))
    return manifest


def _shard_repositories(
    spec: dict[str, Any], parsed: list[dict[str, Any]]
) -> list[str]:
    if "repositories" in spec:
        return spec["repositories"]
    return sorted({row["repository_id"] for row in parsed})


def write_shard(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    number = int(spec["number"])
    records: list[bytes] = spec["records"]
    parsed = [json.loads(line.decode("utf-8")) for line in records]
    repositories = _shard_repositories(spec, parsed)
    records_bytes = write_jsonl(path / "records.jsonl", records)
    counts = {
        "repository_count": len(repositories),
        "record_count": len(records),
        **_state_counts(parsed),
    }
    manifest = {
        "assignment_rule": spec.get("assignment_rule", ASSIGNMENT_RULE),
        "counts": counts,
        "files": {"records.jsonl": _file_info(records_bytes)},
        "inventory_policy_version": spec.get(
            "inventory_policy_version", INVENTORY_POLICY_VERSION
        ),
        "inventory_revision": spec["inventory_revision"],
        "repositories": repositories,
        "schema_version": spec.get("schema_version", SHARD_MANIFEST_SCHEMA_VERSION),
        "shard_count": SHARD_COUNT,
        "shard_number": number,
        "trajectory_schema_version": spec.get(
            "trajectory_schema_version", TRAJECTORY_SCHEMA_VERSION
        ),
    }
    manifest["manifest_sha256"] = digest_manifest(manifest)
    (path / "manifest.json").write_bytes(render_json(manifest))
    return manifest


def build_valid_tree(root: Path) -> tuple[Path, Path]:
    """Write a three-shard fixture and return (inventory_dir, shards_dir)."""
    for number, repository_id in REPOSITORY_IDS.items():
        assert assign_shard(repository_id) == number, repository_id
    records_by_shard = valid_records()
    inventory_dir = root / "inventory"
    shards_dir = root / "shards"
    inventory_manifest = write_inventory(inventory_dir, records_by_shard)
    for number in range(SHARD_COUNT):
        write_shard(
            shards_dir / f"shard-{number}",
            {
                "number": number,
                "inventory_revision": inventory_manifest["snapshot_sha256"],
                "records": records_by_shard[number],
            },
        )
    return inventory_dir, shards_dir
