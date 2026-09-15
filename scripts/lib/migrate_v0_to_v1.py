"""Lossless pr_trajectory_v0 → trajectory-v1 envelope migration.

Maps only values present in the source record. Missing evidence is recorded as
unavailable or the record is refused; timestamps, OIDs, actors, and events are
never invented. Admitted output is schema-valid v1 that also passes
``validate_jsonl --strict-policy``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from validate_jsonl import policy_errors

from .migrate_v0_mapping import (
    MIGRATION_TOOL_VERSION,
    V1_SCHEMA_VERSIONS,
    _candidate_envelope,
    _collect_unavailable,
    _extract_code_state,
    _extract_timestamp,
    _nonempty_str,
    _unknown_event_reason,
    _v1_validator,
    canonical_dumps,
    source_digest,
)


def migrate_record(
    line_bytes: bytes,
    *,
    validator: Any | None = None,
) -> dict[str, Any]:
    """Migrate one JSONL line. Returns an admitted/refused decision dict."""
    try:
        digest, byte_size, source_text = source_digest(line_bytes)
    except UnicodeDecodeError:
        payload = line_bytes.rstrip(b"\r\n")
        return {
            "status": "refused",
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "source_byte_size": len(payload),
            "reason_codes": ["invalid_utf8"],
            "unavailable_fields": [],
            "trajectory_id": None,
            "detail": "source record is not valid UTF-8",
            "output_record": None,
        }

    try:
        parsed = json.loads(source_text)
    except json.JSONDecodeError as exc:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": ["invalid_json"],
            "unavailable_fields": [],
            "trajectory_id": None,
            "detail": f"invalid JSON: {exc}",
            "output_record": None,
        }

    if not isinstance(parsed, dict):
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": ["not_an_object"],
            "unavailable_fields": [],
            "trajectory_id": None,
            "detail": "JSONL record is not an object",
            "output_record": None,
        }

    version = parsed.get("schema_version")
    if version in V1_SCHEMA_VERSIONS:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": ["already_v1"],
            "unavailable_fields": [],
            "trajectory_id": _nonempty_str(parsed.get("trajectory_id")),
            "detail": (
                "already-v1 input is refused (documented no-op: the source is "
                "left unchanged and is not copied to the migrated output)"
            ),
            "output_record": None,
        }

    unknown = _unknown_event_reason(parsed)
    if unknown is not None:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": [unknown],
            "unavailable_fields": _collect_unavailable(parsed),
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": "source contains an event or validation type that was not in the v0 contract",
            "output_record": None,
        }

    timestamp, ts_error = _extract_timestamp(parsed)
    if ts_error is not None:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": [ts_error],
            "unavailable_fields": _collect_unavailable(parsed),
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": (
                "source timestamp is not a parseable UTC instant"
                if ts_error == "malformed_timestamp"
                else "source has no timestamp; refusing rather than fabricating one"
            ),
            "output_record": None,
        }

    code_state, oid_error = _extract_code_state(parsed)
    if oid_error is not None:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": [oid_error],
            "unavailable_fields": _collect_unavailable(parsed),
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": "source commit OID is present but is not a git object id",
            "output_record": None,
        }
    if not code_state:
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": ["unavailable_commit_oid"],
            "unavailable_fields": _collect_unavailable(parsed),
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": (
                "software v1 strict-policy requires a code-state OID; source "
                "has none and the migrator will not invent one"
            ),
            "output_record": None,
        }

    unavailable = _collect_unavailable(parsed)
    built = _candidate_envelope(
        parsed,
        source_text=source_text,
        source_bytes=source_text.encode("utf-8"),
        digest=digest,
        timestamp=timestamp or "",
        code_state=code_state,
        unavailable=unavailable,
    )
    if isinstance(built, str):
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": [built],
            "unavailable_fields": unavailable,
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": f"lossless mapping refused: {built}",
            "output_record": None,
        }

    active_validator = validator if validator is not None else _v1_validator()
    schema_errors = [
        error.message
        for error in sorted(active_validator.iter_errors(built), key=lambda e: list(e.path))
    ]
    policy = policy_errors(built, 1, "migrated")
    if schema_errors or policy:
        reasons = []
        if schema_errors:
            reasons.append("v1_schema")
        if policy:
            reasons.append("strict_policy")
        return {
            "status": "refused",
            "source_sha256": digest,
            "source_byte_size": byte_size,
            "reason_codes": reasons,
            "unavailable_fields": unavailable,
            "trajectory_id": _nonempty_str(parsed.get("id")),
            "detail": "; ".join(schema_errors + policy),
            "output_record": None,
        }

    return {
        "status": "admitted",
        "source_sha256": digest,
        "source_byte_size": byte_size,
        "reason_codes": [],
        "unavailable_fields": unavailable,
        "trajectory_id": built["trajectory_id"],
        "detail": "",
        "output_record": built,
    }


def migrate_jsonl(text: str, *, input_path: str = "input.jsonl") -> tuple[str, dict[str, Any]]:
    """Migrate a JSONL document. Returns (admitted jsonl, report)."""
    validator = _v1_validator()
    raw = text.encode("utf-8")
    file_digest = hashlib.sha256(raw).hexdigest()
    admitted_lines: list[str] = []
    records: list[dict[str, Any]] = []
    line_no = 0
    for raw_line in text.splitlines(keepends=True):
        if not raw_line.strip():
            continue
        line_no += 1
        decision = migrate_record(raw_line.encode("utf-8"), validator=validator)
        row = {
            "detail": decision["detail"],
            "input_path": input_path,
            "line": line_no,
            "reason_codes": list(decision["reason_codes"]),
            "source_sha256": decision["source_sha256"],
            "status": decision["status"],
            "trajectory_id": decision["trajectory_id"],
            "unavailable_fields": list(decision["unavailable_fields"]),
        }
        records.append(row)
        if decision["status"] == "admitted" and decision["output_record"] is not None:
            admitted_lines.append(canonical_dumps(decision["output_record"]))

    admitted_text = ("\n".join(admitted_lines) + "\n") if admitted_lines else ""
    report = {
        "admitted_count": sum(1 for r in records if r["status"] == "admitted"),
        "inputs": [
            {
                "bytes": len(raw),
                "path": input_path,
                "sha256": file_digest,
            }
        ],
        "migration_tool_version": MIGRATION_TOOL_VERSION,
        "records": records,
        "refused_count": sum(1 for r in records if r["status"] == "refused"),
    }
    return admitted_text, report


def migrate_files(
    inputs: list[Path],
    *,
    out_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    """Migrate one or more JSONL files into out_path + report_path."""
    validator = _v1_validator()
    admitted_lines: list[str] = []
    records: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []

    for path in inputs:
        data = path.read_bytes()
        input_rows.append(
            {
                "bytes": len(data),
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        line_no = 0
        for raw_line in data.splitlines(keepends=True):
            if not raw_line.strip():
                continue
            line_no += 1
            decision = migrate_record(raw_line, validator=validator)
            records.append(
                {
                    "detail": decision["detail"],
                    "input_path": str(path),
                    "line": line_no,
                    "reason_codes": list(decision["reason_codes"]),
                    "source_sha256": decision["source_sha256"],
                    "status": decision["status"],
                    "trajectory_id": decision["trajectory_id"],
                    "unavailable_fields": list(decision["unavailable_fields"]),
                }
            )
            if decision["status"] == "admitted" and decision["output_record"] is not None:
                admitted_lines.append(canonical_dumps(decision["output_record"]))

    admitted_text = ("\n".join(admitted_lines) + "\n") if admitted_lines else ""
    report = {
        "admitted_count": sum(1 for r in records if r["status"] == "admitted"),
        "inputs": input_rows,
        "migration_tool_version": MIGRATION_TOOL_VERSION,
        "records": records,
        "refused_count": sum(1 for r in records if r["status"] == "refused"),
    }
    _atomic_write_text(out_path, admitted_text)
    _atomic_write_text(report_path, canonical_dumps(report) + "\n")
    return report


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def resolved_same(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()
