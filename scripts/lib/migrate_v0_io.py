"""Batch JSONL I/O for lossless v0-to-v1 migration."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .migrate_v0_constants import MIGRATION_TOOL_VERSION
from .migrate_v0_record import migrate_record
from .migrate_v0_text import canonical_dumps, iter_jsonl_lines, resolved_same, v1_validator


@dataclass
class _BatchSink:
    admitted_lines: list[str] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)


def migrate_jsonl(text: str, *, input_path: str = "input.jsonl") -> tuple[str, dict[str, Any]]:
    """Migrate a JSONL document. Returns (admitted jsonl, report)."""
    raw = text.encode("utf-8")
    return _migrate_bytes(raw, input_path=input_path)


def migrate_files(
    inputs: list[Path],
    *,
    out_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    """Migrate one or more JSONL files into out_path + report_path."""
    if resolved_same(out_path, report_path):
        raise RuntimeError("output and report paths must be different")
    validator = v1_validator()
    sink = _BatchSink()
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
        _append_file_decisions(data, str(path), validator, sink)
    admitted_text = ("\n".join(sink.admitted_lines) + "\n") if sink.admitted_lines else ""
    report = _report(input_rows, sink.records)
    atomic_write_text(out_path, admitted_text)
    atomic_write_text(report_path, canonical_dumps(report) + "\n")
    return report


def _migrate_bytes(raw: bytes, *, input_path: str) -> tuple[str, dict[str, Any]]:
    validator = v1_validator()
    sink = _BatchSink()
    _append_file_decisions(raw, input_path, validator, sink)
    admitted_text = ("\n".join(sink.admitted_lines) + "\n") if sink.admitted_lines else ""
    file_digest = hashlib.sha256(raw).hexdigest()
    report = _report(
        [{"bytes": len(raw), "path": input_path, "sha256": file_digest}], sink.records
    )
    return admitted_text, report


def _append_file_decisions(
    data: bytes,
    input_path: str,
    validator: Any,
    sink: _BatchSink,
) -> None:
    for line_no, raw_line in iter_jsonl_lines(data):
        if not raw_line.strip():
            continue
        decision = migrate_record(raw_line, validator=validator)
        sink.records.append(
            {
                "detail": decision["detail"],
                "input_path": input_path,
                "line": line_no,
                "reason_codes": list(decision["reason_codes"]),
                "source_sha256": decision["source_sha256"],
                "status": decision["status"],
                "trajectory_id": decision["trajectory_id"],
                "unavailable_fields": list(decision["unavailable_fields"]),
            }
        )
        if decision["status"] == "admitted" and decision["output_record"] is not None:
            sink.admitted_lines.append(canonical_dumps(decision["output_record"]))


def _report(inputs: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "admitted_count": sum(1 for row in records if row["status"] == "admitted"),
        "inputs": inputs,
        "migration_tool_version": MIGRATION_TOOL_VERSION,
        "records": records,
        "refused_count": sum(1 for row in records if row["status"] == "refused"),
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
