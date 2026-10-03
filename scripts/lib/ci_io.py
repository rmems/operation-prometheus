"""Paths and JSONL/hash IO shared by CI contract jobs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
INVENTORY_DIR = ROOT / "datasets" / "inventory" / "v0.7"
JSONL_DIR = ROOT / "datasets" / "jsonl"
MANIFEST_DIR = ROOT / "datasets" / "manifests"
PARQUET_DIR = ROOT / "datasets" / "parquet"
RELEASE_MANIFEST = ROOT / "datasets" / "release" / "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                rows.append((line_number, record))
    return rows


def record_identity(record: dict[str, Any]) -> str | None:
    if record.get("schema_version") in ("1", "1.0", "v1", "1.1", "v1.1"):
        value = record.get("trajectory_id")
    else:
        value = record.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def canonical_trajectory_ids(records: list[dict[str, Any]]) -> set[str]:
    identities = [_canonical_trajectory_id(record) for record in records]
    duplicate = next(
        (identity for identity, count in Counter(identities).items() if count > 1),
        None,
    )
    if duplicate is not None:
        raise ValueError(f"duplicate trajectory_id {duplicate}")
    return set(identities)


def _canonical_trajectory_id(record: dict[str, Any]) -> str:
    identity = record.get("trajectory_id")
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("canonical row has invalid trajectory_id")
    return identity
