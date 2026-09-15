"""Verify shard identity, digests, and inventory membership."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from .corpus_shard_common import (
    ASSIGNMENT_RULE,
    SHARD_MANIFEST_SCHEMA_VERSION,
    TRAJECTORY_SCHEMA_VERSION,
    LoadedShard,
    as_mapping,
    assign_shard,
    count_states,
    digest_manifest,
    file_info,
    load_json_object,
    load_record_lines,
    record_envelope,
    reject_foreign_member,
    require_equal,
)


class Coverage(NamedTuple):
    inventory: dict[str, Any]
    expected_repos: dict[int, set[str]]
    seen_repositories: dict[str, int]
    seen_candidates: dict[str, int]
    shard_count: int


def repos_by_shard(inventory: dict[str, Any], shard_count: int) -> dict[int, set[str]]:
    grouped: dict[int, set[str]] = {number: set() for number in range(shard_count)}
    for repository_id in inventory["repository_ids"]:
        grouped[assign_shard(repository_id, shard_count=shard_count)].add(repository_id)
    return grouped


def _reject_unexpected_shards(found: dict[str, Path], expected: set[str]) -> None:
    unexpected = sorted(name for name in found if name not in expected)
    if unexpected:
        raise ValueError(f"Unexpected corpus shard {unexpected[0]}")


def _required_shard_dirs(found: dict[str, Path], shard_count: int) -> dict[int, Path]:
    missing = [
        number for number in range(shard_count) if f"shard-{number}" not in found
    ]
    if missing:
        raise ValueError(f"Missing corpus shard {missing[0]}")
    return {number: found[f"shard-{number}"] for number in range(shard_count)}


def discover_shard_dirs(shards_dir: Path, shard_count: int) -> dict[int, Path]:
    if not shards_dir.is_dir():
        raise ValueError(f"Missing shards directory {shards_dir}")
    expected = {f"shard-{number}" for number in range(shard_count)}
    found = {path.name: path for path in shards_dir.iterdir() if path.is_dir()}
    _reject_unexpected_shards(found, expected)
    return _required_shard_dirs(found, shard_count)


def _identity_checks(
    shard: LoadedShard, coverage: Coverage
) -> tuple[tuple[Any, Any, str], ...]:
    manifest = shard.manifest
    return (
        (
            manifest.get("shard_number"),
            shard.number,
            f"Shard {shard.number} number mismatch: manifest has {manifest.get('shard_number')!r}",
        ),
        (
            manifest.get("shard_count"),
            coverage.shard_count,
            f"Shard {shard.number} shard_count mismatch",
        ),
        (
            manifest.get("assignment_rule"),
            ASSIGNMENT_RULE,
            f"Shard {shard.number} assignment rule mismatch",
        ),
        (
            manifest.get("schema_version"),
            SHARD_MANIFEST_SCHEMA_VERSION,
            (
                f"Shard {shard.number} schema mismatch: expected "
                f"{SHARD_MANIFEST_SCHEMA_VERSION}, got {manifest.get('schema_version')!r}"
            ),
        ),
        (
            manifest.get("trajectory_schema_version"),
            TRAJECTORY_SCHEMA_VERSION,
            (
                f"Shard {shard.number} schema mismatch: expected trajectory schema "
                f"{TRAJECTORY_SCHEMA_VERSION}, got {manifest.get('trajectory_schema_version')!r}"
            ),
        ),
        (
            manifest.get("inventory_revision"),
            coverage.inventory["revision"],
            f"Shard {shard.number} inventory revision mismatch",
        ),
        (
            manifest.get("inventory_policy_version"),
            coverage.inventory["policy_version"],
            f"Shard {shard.number} inventory policy version mismatch",
        ),
    )


def _verify_shard_identity(shard: LoadedShard, coverage: Coverage) -> None:
    for actual, expected, message in _identity_checks(shard, coverage):
        require_equal(actual, expected, message)


def _records_digest_matches(declared: Any, actual: dict[str, Any]) -> bool:
    if not isinstance(declared, dict):
        return False
    if declared.get("sha256") != actual["sha256"]:
        return False
    return declared.get("bytes") == actual["bytes"]


def _verify_shard_digests(shard: LoadedShard) -> None:
    require_equal(
        shard.manifest.get("manifest_sha256"),
        digest_manifest(shard.manifest),
        f"Shard {shard.number} manifest digest mismatch",
    )
    files = as_mapping(shard.manifest.get("files"))
    actual = file_info(shard.records_bytes)
    if _records_digest_matches(files.get("records.jsonl"), actual):
        return
    raise ValueError(f"Shard {shard.number} records digest mismatch")


def load_shard(path: Path, number: int, coverage: Coverage) -> LoadedShard:
    manifest_path = path / "manifest.json"
    records_path = path / "records.jsonl"
    if not manifest_path.is_file():
        raise ValueError(f"Missing corpus shard {number}")
    if not records_path.is_file():
        raise ValueError(f"Missing corpus shard {number}")
    records_bytes, records = load_record_lines(records_path)
    shard = LoadedShard(
        number, path, load_json_object(manifest_path), records, records_bytes
    )
    _verify_shard_identity(shard, coverage)
    _verify_shard_digests(shard)
    return shard


def _valid_repository_id(item: Any) -> bool:
    if not isinstance(item, str):
        return False
    return bool(item)


def _declared_repositories(shard: LoadedShard) -> list[str]:
    declared = shard.manifest.get("repositories")
    if not isinstance(declared, list):
        raise ValueError(f"Shard {shard.number} repositories list is invalid")
    if not all(_valid_repository_id(item) for item in declared):
        raise ValueError(f"Shard {shard.number} repositories list is invalid")
    require_equal(
        len(declared),
        len(set(declared)),
        f"Duplicate repository in shard {shard.number}",
    )
    require_equal(
        declared,
        sorted(declared),
        f"Shard {shard.number} repositories are not in sorted order",
    )
    return declared


def _claim_repository(
    repository_id: str, shard: LoadedShard, coverage: Coverage
) -> None:
    previous = coverage.seen_repositories.get(repository_id)
    if previous is not None:
        raise ValueError(f"Duplicate repository {repository_id}")
    coverage.seen_repositories[repository_id] = shard.number
    reject_foreign_member(repository_id, shard.number, coverage.shard_count)


def _bind_candidate(
    ids: tuple[str, str], shard: LoadedShard, coverage: Coverage
) -> None:
    candidate_id, repository_id = ids
    if candidate_id in coverage.seen_candidates:
        raise ValueError(f"Duplicate record {candidate_id}")
    coverage.seen_candidates[candidate_id] = shard.number
    expected_repo = coverage.inventory["candidate_repos"].get(candidate_id)
    if expected_repo is None:
        raise ValueError(
            f"Unknown shard record {candidate_id} is not in the frozen inventory"
        )
    require_equal(
        expected_repo,
        repository_id,
        f"Shard record {candidate_id} repository_id does not match the inventory",
    )


def _claim_record(
    entry: tuple[int, bytes, dict[str, Any]],
    shard: LoadedShard,
    coverage: Coverage,
) -> tuple[bytes, str]:
    index, raw, record = entry
    label = f"shard {shard.number} record {index}"
    candidate_id, repository_id = record_envelope(record, label=label)
    reject_foreign_member(repository_id, shard.number, coverage.shard_count)
    _bind_candidate((candidate_id, repository_id), shard, coverage)
    return raw, candidate_id


def _verify_counts(shard: LoadedShard, declared_repos: list[str]) -> None:
    record_objects = [row for _, row in shard.records]
    actual_counts = {
        "repository_count": len(declared_repos),
        "record_count": len(shard.records),
        **count_states(record_objects),
    }
    require_equal(
        shard.manifest.get("counts"),
        actual_counts,
        f"Shard {shard.number} counts do not conserve",
    )


def verify_shard_members(
    shard: LoadedShard, coverage: Coverage
) -> list[tuple[bytes, str]]:
    declared_repos = _declared_repositories(shard)
    for repository_id in declared_repos:
        _claim_repository(repository_id, shard, coverage)
    require_equal(
        set(declared_repos),
        coverage.expected_repos[shard.number],
        f"Shard {shard.number} repositories do not match inventory assignment",
    )
    kept = [
        _claim_record((index, raw, record), shard, coverage)
        for index, (raw, record) in enumerate(shard.records)
    ]
    _verify_counts(shard, declared_repos)
    return kept
