"""Normalize local Hermes traces into deterministic trajectory v1.1 records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .hermes_sanitize import (
    UnsafeUrlError,
    sanitize_query_secrets,
    strip_hidden_reasoning,
)
from .hermes_safety import _safety_reasons, _tool_payload_reasons
from .hermes_output import (
    NORMALIZER_VERSION,
    _emit_record,
    _identity_tuple,
    _independent_terminal,
    _trace_conflicts,
    _trajectory_id,
)
from .hermes_binding import (
    _binding_errors,
    _manifest_schema_errors,
    _raw_record_errors,
    _raw_validator,
    _v1_1_validator,
    _workspace_errors,
)
from .hermes_json import _iter_jsonl_lines, _parse_json_object

__all__ = ["LocalFileBoundary", "NORMALIZER_VERSION", "canonical_dumps", "normalize_files"]

REPORT_SCHEMA_VERSION = "hermes_normalize_report_v1"


@dataclass(frozen=True)
class _LineContext:
    input_path: str
    input_digest: str
    manifest_digest: str
    admission_digest: str
    manifest: dict[str, Any] | None
    file_reasons: list[str]
    seen_keys: dict[tuple[str, str, str, str], int]
    validator: Any
    raw_validator: Any


class LocalFileBoundary:
    """Read-only local-file source. Tests may inject frozen bytes for replay."""

    def __init__(self, opener: Callable[[Path], bytes] | None = None) -> None:
        self._opener = opener

    def read_bytes(self, path: Path | str) -> bytes:
        raw = str(path)
        if _is_remote(raw):
            raise ValueError(f"refusing non-local file path: {raw}")
        resolved = Path(raw).expanduser()
        if self._opener is not None:
            return self._opener(resolved)
        return resolved.read_bytes()


def canonical_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_files(
    *,
    input_path: Path,
    run_manifest_path: Path,
    model_admission_path: Path,
    output_path: Path,
    report_path: Path,
    source: LocalFileBoundary | None = None,
) -> dict[str, Any]:
    """Normalize one Hermes JSONL file. Returns the decision report."""
    _refuse_collisions(
        [input_path, run_manifest_path, model_admission_path],
        output_path,
        report_path,
    )
    boundary = source or LocalFileBoundary()
    input_bytes = boundary.read_bytes(input_path)
    manifest_bytes = boundary.read_bytes(run_manifest_path)
    admission_bytes = boundary.read_bytes(model_admission_path)
    report = _normalize_bytes(
        input_bytes=input_bytes,
        manifest_bytes=manifest_bytes,
        admission_bytes=admission_bytes,
        input_path=str(input_path),
    )
    admitted = [row["output_line"] for row in report.pop("_admitted_lines")]
    admitted_text = ("\n".join(admitted) + "\n") if admitted else ""
    _atomic_write_bytes(output_path, admitted_text.encode("utf-8"))
    _atomic_write_bytes(report_path, (canonical_dumps(report) + "\n").encode("utf-8"))
    return report


def _is_remote(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered.startswith(("http://", "https://", "ftp://")):
        return True
    parsed = urlsplit(raw)
    return bool(parsed.scheme) and parsed.scheme not in {"", "file"}


def _same_file(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _refuse_collisions(
    inputs: list[Path], output_path: Path, report_path: Path
) -> None:
    if _same_file(output_path, report_path):
        raise RuntimeError("output and report paths must be different")
    for source in inputs:
        if _same_file(source, output_path):
            raise RuntimeError(f"refusing to overwrite source file: {source}")
        if _same_file(source, report_path):
            raise RuntimeError(
                f"refusing to overwrite source file with the report: {source}"
            )


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _normalize_bytes(
    *,
    input_bytes: bytes,
    manifest_bytes: bytes,
    admission_bytes: bytes,
    input_path: str,
) -> dict[str, Any]:
    input_digest = sha256_bytes(input_bytes)
    manifest_digest = sha256_bytes(manifest_bytes)
    admission_digest = sha256_bytes(admission_bytes)
    file_reasons: list[str] = []
    manifest, manifest_reason = _parse_json_object(manifest_bytes)
    admission, admission_reason = _parse_json_object(admission_bytes)
    if manifest is None:
        file_reasons.append(manifest_reason or "invalid_json")
    else:
        file_reasons.extend(_manifest_schema_errors(manifest))
        file_reasons.extend(_safety_reasons(manifest))
    if admission is None:
        file_reasons.append(admission_reason or "invalid_json")
    else:
        file_reasons.extend(_safety_reasons(admission))
    if manifest is not None:
        file_reasons.extend(_workspace_errors(manifest))
    if manifest is not None and admission is not None:
        file_reasons.extend(_binding_errors(manifest, admission, admission_digest))

    decisions: list[dict[str, Any]] = []
    admitted_lines: list[str] = []
    seen_keys: dict[tuple[str, str, str, str], int] = {}
    validator = _v1_1_validator()
    raw_validator = _raw_validator()
    context = _LineContext(
        input_path=input_path,
        input_digest=input_digest,
        manifest_digest=manifest_digest,
        admission_digest=admission_digest,
        manifest=manifest,
        file_reasons=file_reasons,
        seen_keys=seen_keys,
        validator=validator,
        raw_validator=raw_validator,
    )
    for line_no, raw_line in _iter_jsonl_lines(input_bytes):
        payload = raw_line.rstrip(b"\r\n")
        if not payload.strip():
            continue
        decision = _normalize_line(payload, line_no=line_no, context=context)
        decisions.append(decision["report_row"])
        if decision["output_line"] is not None:
            admitted_lines.append(decision["output_line"])

    if not decisions:
        empty_reasons = [*file_reasons, "empty_input"]
        decisions.append(
            _decision(
                line_no=0,
                status="rejected",
                reasons=empty_reasons,
                source_sha256=input_digest,
                trajectory_id=None,
                output_line=None,
            )["report_row"]
        )

    report = {
        "accepted_count": sum(1 for row in decisions if row["status"] == "accepted"),
        "admission_report_sha256": admission_digest,
        "input_sha256": input_digest,
        "quarantined_count": sum(
            1 for row in decisions if row["status"] == "quarantined"
        ),
        "records": decisions,
        "rejected_count": sum(1 for row in decisions if row["status"] == "rejected"),
        "run_manifest_sha256": manifest_digest,
        "schema_version": REPORT_SCHEMA_VERSION,
        "_admitted_lines": [{"output_line": line} for line in admitted_lines],
    }
    return report


def _normalize_line(
    payload: bytes,
    *,
    line_no: int,
    context: _LineContext,
) -> dict[str, Any]:
    source_digest = sha256_bytes(payload)
    try:
        return _normalize_line_inner(
            payload,
            line_no=line_no,
            context=context,
            source_digest=source_digest,
        )
    except UnsafeUrlError as exc:
        reason = "secret_leakage" if "credential" in str(exc) else "invalid_record"
        return _decision(
            line_no=line_no,
            status="rejected",
            reasons=[*context.file_reasons, reason],
            source_sha256=source_digest,
            trajectory_id=None,
            output_line=None,
        )
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
        return _decision(
            line_no=line_no,
            status="rejected",
            reasons=[*context.file_reasons, "invalid_record"],
            source_sha256=source_digest,
            trajectory_id=None,
            output_line=None,
        )


def _normalize_line_inner(
    payload: bytes,
    *,
    line_no: int,
    context: _LineContext,
    source_digest: str,
) -> dict[str, Any]:
    parsed, parse_reason = _parse_json_object(payload)
    reasons = list(context.file_reasons)
    if parsed is None:
        reasons.append(parse_reason or "invalid_json")
        return _line_decision(line_no, "rejected", reasons, source_digest)
    sanitized, identity, terminal = _prepare_candidate(
        parsed, line_no=line_no, context=context, reasons=reasons
    )
    status = _candidate_status(reasons, terminal)
    if status != "accepted" or context.manifest is None:
        return _decision(
            line_no=line_no,
            status=_final_nonaccepted_status(status, reasons),
            reasons=_unique_reasons(reasons),
            source_sha256=source_digest,
            trajectory_id=_trajectory_id(parsed) if identity is not None else None,
            output_line=None,
        )
    record = _emit_record(
        sanitized,
        manifest=context.manifest,
        input_digest=context.input_digest,
        manifest_digest=context.manifest_digest,
        admission_digest=context.admission_digest,
        raw_trace_sha256=source_digest,
        terminal=terminal,
    )
    reasons.extend(_emitted_record_reasons(record, context.validator))
    if reasons:
        return _decision(
            line_no=line_no,
            status="rejected",
            reasons=_unique_reasons(reasons),
            source_sha256=source_digest,
            trajectory_id=record.get("trajectory_id"),
            output_line=None,
        )
    return _decision(
        line_no=line_no,
        status="accepted",
        reasons=[],
        source_sha256=source_digest,
        trajectory_id=record["trajectory_id"],
        output_line=canonical_dumps(record),
        extra={"input_path": context.input_path},
    )


def _prepare_candidate(
    parsed: dict[str, Any],
    *,
    line_no: int,
    context: _LineContext,
    reasons: list[str],
) -> tuple[dict[str, Any], tuple[str, str, str, str] | None, str | None]:
    reasons.extend(_raw_record_errors(parsed, context.raw_validator))
    identity = _record_identity(parsed, line_no, context, reasons)
    reasons.extend(_tool_payload_reasons(parsed))
    reasons.extend(_safety_reasons(parsed, allow_hidden=True))
    sanitized = strip_hidden_reasoning(sanitize_query_secrets(parsed))
    reasons.extend(_safety_reasons(sanitized, allow_hidden=False))
    terminal = _manifest_terminal(parsed, context.manifest, reasons)
    return sanitized, identity, terminal


def _record_identity(
    parsed: dict[str, Any],
    line_no: int,
    context: _LineContext,
    reasons: list[str],
) -> tuple[str, str, str, str] | None:
    if "invalid_hermes_record" in reasons:
        return None
    identity = _identity_tuple(parsed)
    if identity in context.seen_keys:
        reasons.append("duplicate_record")
    else:
        context.seen_keys[identity] = line_no
    return identity


def _manifest_terminal(
    parsed: dict[str, Any],
    manifest: dict[str, Any] | None,
    reasons: list[str],
) -> str | None:
    if manifest is None:
        reasons.append("invalid_manifest")
        return None
    reasons.extend(_trace_conflicts(parsed, manifest))
    terminal, verifier_reasons = _independent_terminal(manifest, parsed)
    reasons.extend(verifier_reasons)
    return terminal


def _candidate_status(reasons: list[str], terminal: str | None) -> str:
    if terminal is None:
        reasons.append("unverified")
        return "quarantined"
    return "rejected" if reasons else "accepted"


def _final_nonaccepted_status(status: str, reasons: list[str]) -> str:
    if status == "accepted":
        reasons.append("invalid_manifest")
        return "rejected"
    if status == "quarantined" and any(code != "unverified" for code in reasons):
        return "rejected"
    return status


def _emitted_record_reasons(record: dict[str, Any], validator: Any) -> list[str]:
    reasons = _safety_reasons(record, allow_hidden=False)
    if _schema_errors(record, validator):
        reasons.append("schema")
    return reasons


def _line_decision(
    line_no: int, status: str, reasons: list[str], source_digest: str
) -> dict[str, Any]:
    return _decision(
        line_no=line_no,
        status=status,
        reasons=reasons,
        source_sha256=source_digest,
        trajectory_id=None,
        output_line=None,
    )


def _decision(
    *,
    line_no: int,
    status: str,
    reasons: list[str],
    source_sha256: str,
    trajectory_id: str | None,
    output_line: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del extra
    row = {
        "line": line_no,
        "reason_codes": _unique_reasons(reasons),
        "source_sha256": source_sha256,
        "status": status,
        "trajectory_id": trajectory_id,
    }
    return {"output_line": output_line, "report_row": row}


def _unique_reasons(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for reason in reasons:
        if not reason or reason in seen:
            continue
        seen.add(reason)
        out.append(reason)
    return out


def _schema_errors(record: dict[str, Any], validator: Any) -> list[str]:
    if validator is None:
        return ["jsonschema_missing"]
    errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
    return [error.message for error in errors]
