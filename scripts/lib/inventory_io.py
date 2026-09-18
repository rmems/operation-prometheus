"""JSONL I/O helpers for collector inventory files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        row = _parse_jsonl_row(path, lineno, text)
        rows.append(row)
    return rows


def _parse_jsonl_row(path: Path, lineno: int, text: str) -> dict[str, Any]:
    try:
        row = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{lineno} is not valid JSON") from exc
    if not isinstance(row, dict):
        raise ValueError(f"{path}:{lineno} is not a JSON object")
    return row


def resolve_inventory_path(path: Path) -> Path:
    """Accept a candidates JSONL file or a ledger directory containing one."""
    path = Path(path)
    if path.is_dir():
        return _candidates_in_dir(path)
    if not path.is_file():
        raise FileNotFoundError(f"Inventory not found: {path}")
    return path


def _candidates_in_dir(path: Path) -> Path:
    candidate = path / "candidates.jsonl"
    if not candidate.is_file():
        raise FileNotFoundError(f"No candidates.jsonl in inventory directory {path}")
    return candidate


def inventory_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
