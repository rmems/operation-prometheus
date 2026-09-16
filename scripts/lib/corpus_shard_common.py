"""Shared constants and primitives for corpus-shard merge."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, NamedTuple

from .eligibility_common import LEDGER_STATES
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


class LoadedShard(NamedTuple):
    number: int
    path: Path
    manifest: dict[str, Any]
    records: list[tuple[bytes, dict[str, Any]]]
    records_bytes: bytes


def assign_shard(repository_id: str, *, shard_count: int = SHARD_COUNT) -> int:
    """Return the deterministic shard for an immutable GitHub repository node ID."""
    require_locked_shard_count(shard_count)
    digest = hashlib.sha256(repository_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count


def require_locked_shard_count(shard_count: int) -> None:
    if shard_count != SHARD_COUNT:
        raise ValueError(
            f"Unsupported shard count {shard_count}; assignment rule is locked to {ASSIGNMENT_RULE}"
        )


def digest_manifest(manifest: dict[str, Any]) -> str:
    """SHA-256 of the canonical manifest with the self-digest field omitted."""
    payload = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    return sha256_json(payload)


def file_info(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def empty_state_counts() -> dict[str, int]:
    return {state: 0 for state in STATE_COUNT_FIELDS}


def count_states(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = empty_state_counts()
    for row in records:
        state = str(row.get("state") or "")
        if state not in counts:
            raise ValueError(f"Unknown ledger state {state!r}")
        counts[state] += 1
    return counts


def load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def require_text(value: Any, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(message)
    if not value.strip():
        raise ValueError(message)
    return value


def require_field(row: dict[str, Any], field: str, *, label: str) -> str:
    return require_text(row.get(field), f"{label} is missing {field}")


def require_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise ValueError(message)


def split_jsonl_lines(data: bytes, *, label: str) -> list[bytes]:
    body = data[:-1] if data.endswith(b"\n") else data
    if not body:
        return []
    lines = body.split(b"\n")
    blank = next(
        (index for index, line in enumerate(lines, start=1) if not line.strip()), None
    )
    if blank is not None:
        raise ValueError(f"{label}:{blank}: blank JSONL line")
    return lines


def parse_jsonl_object(line: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid JSONL") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: JSONL row must be an object")
    return value


def load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    lines = split_jsonl_lines(path.read_bytes(), label=path.name)
    return [
        parse_jsonl_object(line, label=f"{path.name}:{index}")
        for index, line in enumerate(lines, start=1)
    ]


def load_record_lines(path: Path) -> tuple[bytes, list[tuple[bytes, dict[str, Any]]]]:
    data = path.read_bytes()
    lines = split_jsonl_lines(data, label=path.name)
    pairs = [
        (line, parse_jsonl_object(line, label=f"{path.name}:{index}"))
        for index, line in enumerate(lines, start=1)
    ]
    return data, pairs


def reject_foreign_member(
    repository_id: str, shard_number: int, shard_count: int
) -> None:
    assigned = assign_shard(repository_id, shard_count=shard_count)
    if assigned == shard_number:
        return
    raise ValueError(
        f"Foreign-shard member {repository_id} in shard {shard_number} "
        f"(wrong modulus {assigned})"
    )


def record_envelope(record: dict[str, Any], *, label: str) -> tuple[str, str]:
    require_equal(
        record.get("schema_version"),
        RECORD_SCHEMA_VERSION,
        (
            f"{label} schema mismatch: expected "
            f"{RECORD_SCHEMA_VERSION}, got {record.get('schema_version')!r}"
        ),
    )
    candidate_id = require_field(record, "candidate_id", label=label)
    repository_id = require_field(record, "repository_id", label=label)
    state = require_field(record, "state", label=label)
    if state not in LEDGER_STATES:
        raise ValueError(f"{label} has unknown ledger state {state!r}")
    reasons = record.get("reason_codes")
    if not isinstance(reasons, list):
        raise ValueError(f"{label} is missing reason_codes")
    if not reasons:
        raise ValueError(f"{label} is missing reason_codes")
    return candidate_id, repository_id
