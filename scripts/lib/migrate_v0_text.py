"""JSON and byte helpers for lossless v0-to-v1 migration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from validate_jsonl import SCHEMA_V1_PATH, load_schema

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised at CLI startup
    jsonschema = None


def canonical_dumps(obj: object) -> str:
    """Stable JSON for byte-identical reruns."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def source_digest(line_bytes: bytes) -> tuple[str, int, str]:
    """Return (sha256 hex, byte size, utf-8 text) for a JSONL record line."""
    payload = line_bytes.rstrip(b"\r\n")
    return hashlib.sha256(payload).hexdigest(), len(payload), payload.decode("utf-8")


def reject_nonfinite(name: str) -> None:
    """Refuse NaN/Infinity so admitted output stays standard JSON."""
    raise ValueError(f"non-finite JSON constant: {name}")


def parse_json_object(source_text: str) -> tuple[dict[str, Any] | None, str, str]:
    """Parse one JSON object. Returns (object, reason_code, detail)."""
    try:
        parsed = json.loads(source_text, parse_constant=reject_nonfinite)
    except json.JSONDecodeError as exc:
        return None, "invalid_json", f"invalid JSON: {exc}"
    except ValueError as exc:
        return None, "invalid_json", str(exc)
    if not isinstance(parsed, dict):
        return None, "not_an_object", "JSONL record is not an object"
    try:
        canonical_dumps(parsed).encode("utf-8")
    except UnicodeEncodeError:
        return None, "unencodable_json", "parsed JSON is not UTF-8 encodable"
    return parsed, "", ""


def v1_validator() -> Any:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: pip install jsonschema")
    schema = load_schema(SCHEMA_V1_PATH)
    return jsonschema.Draft7Validator(
        schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )


def is_v1_schema_version(value: object) -> bool:
    from .migrate_v0_constants import V1_SCHEMA_VERSIONS

    return isinstance(value, str) and value in V1_SCHEMA_VERSIONS


def iter_jsonl_lines(data: bytes) -> list[tuple[int, bytes]]:
    """Split only on LF (optional CR), preserving physical line numbers."""
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


def resolved_same(left: Any, right: Any) -> bool:
    return left.resolve() == right.resolve()
