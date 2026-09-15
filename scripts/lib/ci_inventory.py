"""Frozen-inventory hash and candidate-index helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ci_io import load_jsonl, sha256_file
from .eligibility_common import LEDGER_STATES


def load_inventory_candidates(inventory_dir: Path) -> list[dict[str, Any]]:
    return [row for _, row in load_jsonl(inventory_dir / "candidates.jsonl")]


def load_inventory_repositories(inventory_dir: Path) -> list[dict[str, Any]]:
    return [row for _, row in load_jsonl(inventory_dir / "repositories.jsonl")]


def _index_one_alias(
    index: dict[tuple[str, int], dict[str, Any]],
    alias: Any,
    number: Any,
    candidate: dict[str, Any],
) -> None:
    if not isinstance(alias, str):
        return
    if not alias:
        return
    index[(alias.casefold(), number)] = candidate


def _index_aliases(
    index: dict[tuple[str, int], dict[str, Any]],
    candidate: dict[str, Any],
    number: Any,
) -> None:
    for alias in candidate.get("repository_aliases") or []:
        _index_one_alias(index, alias, number, candidate)


def _index_primary(
    index: dict[tuple[str, int], dict[str, Any]], candidate: dict[str, Any]
) -> Any:
    repo = str(candidate.get("repository_name_with_owner") or "").casefold()
    number = candidate.get("pull_request_number")
    if not repo:
        return number
    if isinstance(number, int):
        index[(repo, number)] = candidate
    return number


def candidate_index(
    candidates: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for candidate in candidates:
        number = _index_primary(index, candidate)
        _index_aliases(index, candidate, number)
    return index


def candidate_reason_errors(candidate: dict[str, Any]) -> list[str]:
    state = candidate.get("state")
    if state not in LEDGER_STATES:
        return [
            f"candidate {candidate.get('candidate_id')} has unknown state {state!r}"
        ]
    errors: list[str] = []
    primary = candidate.get("primary_reason")
    if not isinstance(primary, str):
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing primary_reason"
        )
    elif not primary.strip():
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing primary_reason"
        )
    reasons = candidate.get("reason_codes")
    if not isinstance(reasons, list):
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing reason_codes"
        )
    elif not reasons:
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing reason_codes"
        )
    return errors


def _byte_size_error(name: str, meta: Any, size: int) -> str | None:
    declared_bytes = (meta or {}).get("bytes")
    if declared_bytes is None:
        return None
    if declared_bytes == size:
        return None
    return f"{name} byte size mismatch: declared {declared_bytes} actual {size}"


def _inventory_missing_or_hash(inventory_dir: Path, name: str, meta: Any) -> list[str]:
    path = inventory_dir / name
    if not path.is_file():
        return [f"inventory file missing: {name}"]
    digest = sha256_file(path)
    declared = str((meta or {}).get("sha256") or "")
    errors: list[str] = []
    if digest != declared:
        errors.append(f"{name} sha256 mismatch: declared {declared} actual {digest}")
    byte_error = _byte_size_error(name, meta, path.stat().st_size)
    if byte_error:
        errors.append(byte_error)
    return errors


def inventory_file_hash_errors(inventory_dir: Path) -> list[str]:
    manifest = json.loads((inventory_dir / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for name, meta in (manifest.get("files") or {}).items():
        errors.extend(_inventory_missing_or_hash(inventory_dir, name, meta))
    return errors


def _parquet_entries(files: Any) -> list[tuple[str, Any]]:
    if isinstance(files, dict):
        return list(files.items())
    if not isinstance(files, list):
        return []
    rows: list[tuple[str, Any]] = []
    for item in files:
        if isinstance(item, dict):
            rows.append((str(item.get("path") or ""), item))
    return rows


def _resolve_parquet_path(name: str, parquet_dir: Path) -> Path:
    path = Path(name)
    if not path.is_absolute():
        path = parquet_dir / name
    named = parquet_dir / Path(name).name
    if path.is_file():
        return path
    return named


def _one_parquet_error(name: str, meta: Any, parquet_dir: Path) -> str | None:
    path = _resolve_parquet_path(name, parquet_dir)
    if not path.is_file():
        return f"release artifact missing: {name}"
    declared = str((meta or {}).get("sha256") or "")
    if not declared:
        return None
    if sha256_file(path) != declared:
        return f"{path.name} sha256 does not match release manifest"
    return None


def parquet_hash_errors(release_manifest: Path, parquet_dir: Path) -> list[str]:
    if not release_manifest.is_file():
        return []
    manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
    files = manifest.get("files") or manifest.get("parquet") or {}
    errors: list[str] = []
    for name, meta in _parquet_entries(files):
        message = _one_parquet_error(name, meta, parquet_dir)
        if message:
            errors.append(message)
    return errors
