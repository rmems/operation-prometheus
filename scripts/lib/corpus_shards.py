"""Deterministic merge of Operation Prometheus corpus shards.

Shard extractors (#56/#57/#58) own record bytes. This module verifies
assignment, inventory coverage, and manifests, then concatenates those
bytes into one canonical global JSONL plus a digest-pinned manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, NamedTuple

from .eligibility_common import LEDGER_STATES
from .eligibility_render import render_json
from .source_inventory_common import sha256_json

SHARD_COUNT = 3
ASSIGNMENT_RULE = "int(sha256(github_repository_node_id)[0:8], 16) % 3"
RECORD_SCHEMA_VERSION = "corpus_shard_record_v1"
SHARD_MANIFEST_SCHEMA_VERSION = "corpus_shard_manifest_v1"
GLOBAL_MANIFEST_SCHEMA_VERSION = "corpus_global_manifest_v1"
TRAJECTORY_SCHEMA_VERSION = "1"
INVENTORY_MANIFEST_SCHEMA_VERSION = "eligibility_manifest_v1"
STATE_COUNT_FIELDS = (
    "included_positive",
    "included_negative",
    "quarantined",
    "excluded",
    "watchlist_open",
)


def assign_shard(repository_id: str, *, shard_count: int = SHARD_COUNT) -> int:
    """Return the deterministic shard for an immutable GitHub repository node ID."""
    if shard_count != SHARD_COUNT:
        raise ValueError(
            f"Unsupported shard count {shard_count}; assignment rule is locked to {ASSIGNMENT_RULE}"
        )
    digest = hashlib.sha256(repository_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count


def digest_manifest(manifest: dict[str, Any]) -> str:
    """SHA-256 of the canonical manifest with the self-digest field omitted."""
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256_json(payload)


class _LoadedShard(NamedTuple):
    number: int
    path: Path
    manifest: dict[str, Any]
    records: list[tuple[bytes, dict[str, Any]]]
    records_bytes: bytes


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _split_jsonl_lines(data: bytes, *, label: str) -> list[bytes]:
    if data.endswith(b"\n"):
        body = data[:-1]
    else:
        body = data
    if not body:
        return []
    lines = body.split(b"\n")
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"{label}:{index}: blank JSONL line")
    return lines


def _load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(_split_jsonl_lines(path.read_bytes(), label=path.name), start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path.name}:{index}: invalid JSONL") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{index}: JSONL row must be an object")
        rows.append(value)
    return rows


def _load_record_lines(path: Path) -> tuple[bytes, list[tuple[bytes, dict[str, Any]]]]:
    data = path.read_bytes()
    pairs: list[tuple[bytes, dict[str, Any]]] = []
    for index, line in enumerate(_split_jsonl_lines(data, label=path.name), start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path.name}:{index}: invalid JSONL") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{index}: JSONL row must be an object")
        pairs.append((line, value))
    return data, pairs


def _file_info(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _empty_state_counts() -> dict[str, int]:
    return {state: 0 for state in STATE_COUNT_FIELDS}


def _count_states(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = _empty_state_counts()
    for row in records:
        state = str(row.get("state") or "")
        if state not in counts:
            raise ValueError(f"Unknown ledger state {state!r}")
        counts[state] += 1
    return counts


def _require_str(row: dict[str, Any], field: str, *, label: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing {field}")
    return value


def _load_inventory(inventory_dir: Path) -> dict[str, Any]:
    manifest_path = inventory_dir / "manifest.json"
    repositories_path = inventory_dir / "repositories.jsonl"
    candidates_path = inventory_dir / "candidates.jsonl"
    for path in (manifest_path, repositories_path, candidates_path):
        if not path.is_file():
            raise ValueError(f"Missing inventory file {path.name}")
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != INVENTORY_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Inventory schema mismatch: expected "
            f"{INVENTORY_MANIFEST_SCHEMA_VERSION}, got {manifest.get('schema_version')!r}"
        )
    revision = manifest.get("snapshot_sha256")
    policy_version = manifest.get("policy_version")
    if not isinstance(revision, str) or not revision:
        raise ValueError("Inventory manifest is missing inventory revision (snapshot_sha256)")
    if not isinstance(policy_version, str) or not policy_version:
        raise ValueError("Inventory manifest is missing policy_version")
    repositories_data = repositories_path.read_bytes()
    candidates_data = candidates_path.read_bytes()
    files = manifest.get("files") or {}
    for name, data in (
        ("repositories.jsonl", repositories_data),
        ("candidates.jsonl", candidates_data),
    ):
        declared = files.get(name) if isinstance(files, dict) else None
        if not isinstance(declared, dict):
            continue
        actual = _file_info(data)
        if declared.get("sha256") != actual["sha256"] or declared.get("bytes") != actual["bytes"]:
            raise ValueError(f"Inventory {name} digest mismatch")
    repositories = _load_jsonl_objects(repositories_path)
    candidates = _load_jsonl_objects(candidates_path)
    repository_ids = [_require_str(row, "repository_id", label=f"repository[{index}]")
                      for index, row in enumerate(repositories)]
    if len(set(repository_ids)) != len(repository_ids):
        raise ValueError("Inventory repositories.jsonl contains duplicate repository_id values")
    candidate_ids: list[str] = []
    candidate_repos: dict[str, str] = {}
    for index, row in enumerate(candidates):
        cid = _require_str(row, "candidate_id", label=f"candidate[{index}]")
        repo_id = _require_str(row, "repository_id", label=f"candidate[{index}]")
        candidate_ids.append(cid)
        candidate_repos[cid] = repo_id
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Inventory candidates.jsonl contains duplicate candidate_id values")
    return {
        "revision": revision,
        "policy_version": policy_version,
        "repository_ids": repository_ids,
        "candidate_ids": candidate_ids,
        "candidate_repos": candidate_repos,
    }


def _discover_shard_dirs(shards_dir: Path, shard_count: int) -> dict[int, Path]:
    if not shards_dir.is_dir():
        raise ValueError(f"Missing shards directory {shards_dir}")
    expected = {f"shard-{number}" for number in range(shard_count)}
    found = {path.name: path for path in shards_dir.iterdir() if path.is_dir()}
    unexpected = sorted(name for name in found if name not in expected)
    if unexpected:
        raise ValueError(f"Unexpected corpus shard {unexpected[0]}")
    missing = [number for number in range(shard_count) if f"shard-{number}" not in found]
    if missing:
        raise ValueError(f"Missing corpus shard {missing[0]}")
    return {number: found[f"shard-{number}"] for number in range(shard_count)}


def _verify_shard_identity(
    manifest: dict[str, Any],
    *,
    number: int,
    shard_count: int,
    inventory: dict[str, Any],
) -> None:
    declared_number = manifest.get("shard_number")
    if declared_number != number:
        raise ValueError(
            f"Shard {number} number mismatch: manifest has {declared_number!r}"
        )
    if manifest.get("shard_count") != shard_count:
        raise ValueError(f"Shard {number} shard_count mismatch")
    if manifest.get("assignment_rule") != ASSIGNMENT_RULE:
        raise ValueError(f"Shard {number} assignment rule mismatch")
    if manifest.get("schema_version") != SHARD_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"Shard {number} schema mismatch: expected "
            f"{SHARD_MANIFEST_SCHEMA_VERSION}, got {manifest.get('schema_version')!r}"
        )
    if manifest.get("trajectory_schema_version") != TRAJECTORY_SCHEMA_VERSION:
        raise ValueError(
            f"Shard {number} schema mismatch: expected trajectory schema "
            f"{TRAJECTORY_SCHEMA_VERSION}, got {manifest.get('trajectory_schema_version')!r}"
        )
    if manifest.get("inventory_revision") != inventory["revision"]:
        raise ValueError(f"Shard {number} inventory revision mismatch")
    if manifest.get("inventory_policy_version") != inventory["policy_version"]:
        raise ValueError(f"Shard {number} inventory policy version mismatch")


def _verify_shard_digests(
    manifest: dict[str, Any],
    records_bytes: bytes,
    *,
    number: int,
) -> None:
    declared_digest = manifest.get("manifest_sha256")
    actual_digest = digest_manifest(manifest)
    if declared_digest != actual_digest:
        raise ValueError(f"Shard {number} manifest digest mismatch")
    files = manifest.get("files") or {}
    declared_records = files.get("records.jsonl") if isinstance(files, dict) else None
    actual_records = _file_info(records_bytes)
    if not isinstance(declared_records, dict) or (
        declared_records.get("sha256") != actual_records["sha256"]
        or declared_records.get("bytes") != actual_records["bytes"]
    ):
        raise ValueError(f"Shard {number} records digest mismatch")


def _verify_record_envelope(record: dict[str, Any], *, label: str) -> tuple[str, str, str]:
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise ValueError(
            f"{label} schema mismatch: expected "
            f"{RECORD_SCHEMA_VERSION}, got {record.get('schema_version')!r}"
        )
    candidate_id = _require_str(record, "candidate_id", label=label)
    repository_id = _require_str(record, "repository_id", label=label)
    state = _require_str(record, "state", label=label)
    if state not in LEDGER_STATES:
        raise ValueError(f"{label} has unknown ledger state {state!r}")
    reasons = record.get("reason_codes")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(f"{label} is missing reason_codes")
    return candidate_id, repository_id, state


def _load_shard(
    path: Path,
    *,
    number: int,
    shard_count: int,
    inventory: dict[str, Any],
) -> _LoadedShard:
    manifest_path = path / "manifest.json"
    records_path = path / "records.jsonl"
    if not manifest_path.is_file() or not records_path.is_file():
        raise ValueError(f"Missing corpus shard {number}")
    manifest = _load_json(manifest_path)
    _verify_shard_identity(
        manifest, number=number, shard_count=shard_count, inventory=inventory
    )
    records_bytes, records = _load_record_lines(records_path)
    _verify_shard_digests(manifest, records_bytes, number=number)
    return _LoadedShard(number, path, manifest, records, records_bytes)


def _inventory_repos_by_shard(
    inventory: dict[str, Any],
    shard_count: int,
) -> dict[int, set[str]]:
    grouped: dict[int, set[str]] = {number: set() for number in range(shard_count)}
    for repository_id in inventory["repository_ids"]:
        grouped[assign_shard(repository_id, shard_count=shard_count)].add(repository_id)
    return grouped


def _verify_shard_members(
    shard: _LoadedShard,
    *,
    inventory: dict[str, Any],
    expected_repos: set[str],
    seen_repositories: dict[str, int],
    seen_candidates: dict[str, int],
    shard_count: int,
) -> list[tuple[bytes, str]]:
    declared_repos = shard.manifest.get("repositories")
    if not isinstance(declared_repos, list) or any(
        not isinstance(item, str) or not item for item in declared_repos
    ):
        raise ValueError(f"Shard {shard.number} repositories list is invalid")
    if len(declared_repos) != len(set(declared_repos)):
        raise ValueError(f"Duplicate repository in shard {shard.number}")
    if declared_repos != sorted(declared_repos):
        raise ValueError(f"Shard {shard.number} repositories are not in sorted order")

    for repository_id in declared_repos:
        previous = seen_repositories.get(repository_id)
        if previous is not None:
            raise ValueError(f"Duplicate repository {repository_id}")
        seen_repositories[repository_id] = shard.number
        assigned = assign_shard(repository_id, shard_count=shard_count)
        if assigned != shard.number:
            raise ValueError(
                f"Foreign-shard member {repository_id} in shard {shard.number} "
                f"(wrong modulus {assigned})"
            )
    if set(declared_repos) != expected_repos:
        raise ValueError(
            f"Shard {shard.number} repositories do not match inventory assignment"
        )

    kept: list[tuple[bytes, str]] = []
    record_objects = [row for _, row in shard.records]
    for index, (raw, record) in enumerate(shard.records):
        label = f"shard {shard.number} record {index}"
        candidate_id, repository_id, _state = _verify_record_envelope(record, label=label)
        assigned = assign_shard(repository_id, shard_count=shard_count)
        if assigned != shard.number:
            raise ValueError(
                f"Foreign-shard member {repository_id} in shard {shard.number} "
                f"(wrong modulus {assigned})"
            )
        previous = seen_candidates.get(candidate_id)
        if previous is not None:
            raise ValueError(f"Duplicate record {candidate_id}")
        seen_candidates[candidate_id] = shard.number
        expected_repo = inventory["candidate_repos"].get(candidate_id)
        if expected_repo is None:
            raise ValueError(
                f"Unknown shard record {candidate_id} is not in the frozen inventory"
            )
        if expected_repo != repository_id:
            raise ValueError(
                f"Shard record {candidate_id} repository_id does not match the inventory"
            )
        kept.append((raw, candidate_id))

    declared_counts = shard.manifest.get("counts")
    actual_counts = {
        "repository_count": len(declared_repos),
        "record_count": len(shard.records),
        **_count_states(record_objects),
    }
    if declared_counts != actual_counts:
        raise ValueError(f"Shard {shard.number} counts do not conserve")
    return kept


def _shard_summary(shard: _LoadedShard) -> dict[str, Any]:
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


def merge_corpus_shards(
    inventory_dir: Path,
    shards_dir: Path,
    *,
    shard_count: int = SHARD_COUNT,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Verify shards against the frozen inventory and emit global artifacts."""
    if shard_count != SHARD_COUNT:
        raise ValueError(
            f"Unsupported shard count {shard_count}; assignment rule is locked to {ASSIGNMENT_RULE}"
        )
    inventory = _load_inventory(inventory_dir)
    shard_dirs = _discover_shard_dirs(shards_dir, shard_count)
    expected_repos = _inventory_repos_by_shard(inventory, shard_count)
    shards = [
        _load_shard(
            shard_dirs[number],
            number=number,
            shard_count=shard_count,
            inventory=inventory,
        )
        for number in range(shard_count)
    ]

    seen_repositories: dict[str, int] = {}
    seen_candidates: dict[str, int] = {}
    preserved: list[tuple[bytes, str]] = []
    for shard in shards:
        preserved.extend(
            _verify_shard_members(
                shard,
                inventory=inventory,
                expected_repos=expected_repos[shard.number],
                seen_repositories=seen_repositories,
                seen_candidates=seen_candidates,
                shard_count=shard_count,
            )
        )

    uncovered = [cid for cid in inventory["candidate_ids"] if cid not in seen_candidates]
    if uncovered:
        raise ValueError(f"Unaccounted inventory row {uncovered[0]}")

    preserved.sort(key=lambda item: item[1])
    record_lines = [raw for raw, _candidate_id in preserved]
    records_bytes = b"".join(line + b"\n" for line in record_lines)
    state_counts = _empty_state_counts()
    for shard in shards:
        for field in STATE_COUNT_FIELDS:
            state_counts[field] += int(shard.manifest["counts"][field])
    counts = {
        "repository_count": len(inventory["repository_ids"]),
        "record_count": len(record_lines),
        **state_counts,
    }
    manifest = {
        "schema_version": GLOBAL_MANIFEST_SCHEMA_VERSION,
        "provider": "github",
        "shard_count": shard_count,
        "assignment_rule": ASSIGNMENT_RULE,
        "inventory_revision": inventory["revision"],
        "inventory_policy_version": inventory["policy_version"],
        "trajectory_schema_version": TRAJECTORY_SCHEMA_VERSION,
        "counts": counts,
        "exclusion_total": state_counts["excluded"],
        "quarantine_total": state_counts["quarantined"],
        "shards": [_shard_summary(shard) for shard in shards],
        "files": {"records.jsonl": _file_info(records_bytes)},
    }
    manifest["manifest_sha256"] = digest_manifest(manifest)
    rendered = {
        "records.jsonl": records_bytes,
        "manifest.json": render_json(manifest),
    }
    return manifest, rendered
