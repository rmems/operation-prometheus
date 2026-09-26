"""Strict JSON and JSONL parsing for Hermes trace input."""

from __future__ import annotations

import json
import math
from typing import Any

def _iter_jsonl_lines(data: bytes) -> list[tuple[int, bytes]]:
    rows: list[tuple[int, bytes]] = []
    start = 0
    line_no = 1
    while start < len(data):
        newline = data.find(b"\n", start)
        if newline == -1:
            rows.append((line_no, data[start:]))
            break
        rows.append((line_no, data[start : newline + 1]))
        start = newline + 1
        line_no += 1
    return rows


def _parse_json_object(payload: bytes) -> tuple[dict[str, Any] | None, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, "invalid_json"
    try:
        parsed = json.loads(
            text,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_unique_object,
        )
    except json.JSONDecodeError:
        return None, "invalid_json"
    except ValueError as exc:
        message = str(exc)
        if "duplicate JSON object key" in message:
            return None, "duplicate_key"
        return None, "invalid_json"
    if _contains_nonfinite(parsed):
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "invalid_json"
    return parsed, ""


def _unique_object(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    seen: set[Any] = set()
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON object key: {key}")
        seen.add(key)
        parsed[key] = value
    return parsed


def _reject_nonfinite(name: str) -> None:
    raise ValueError(f"non-finite JSON constant: {name}")


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, dict):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite(item) for item in value)
    return False

