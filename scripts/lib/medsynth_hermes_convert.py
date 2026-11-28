"""Convert medsynth Hermes session records into first-party artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hermes_binding import _raw_record_errors, _raw_validator
from .hermes_json import _parse_json_object
from .hermes_normalize import (
    LocalFileBoundary,
    _atomic_write_pair,
    _refuse_collisions,
    canonical_dumps,
    sha256_bytes,
)
from .hermes_safety import _safety_reasons, _tool_payload_reasons
from .hermes_sanitize import (
    UnsafeUrlError,
    sanitize_query_secrets,
    strip_hidden_reasoning,
)
from .medsynth_hermes_artifact import (
    _artifact_errors,
    _artifact_validator,
    _build_artifact,
)
from .medsynth_hermes_common import (
    CONVERTER_VERSION,
    REPORT_SCHEMA_VERSION,
    _BatchContext,
    _ConversionInput,
    _SessionRead,
    _canonical_sha256,
    _has_lone_surrogate,
    _nonempty_str,
    _optional_str,
    _refusal,
    _unique_reasons,
)
from .medsynth_hermes_validate import (
    _cross_bind_errors,
    _envelope_errors,
    _manifest_duplicate_errors,
    _manifest_errors,
    _safe_session_file,
    _session_binding,
)


def convert_files(**options: Any) -> dict[str, Any]:
    """Convert all Hermes sessions bound by one medsynth batch manifest."""
    paths, source = _conversion_options(options)
    batch_manifest_path, session_root, output_path, report_path = paths
    boundary = source or LocalFileBoundary()
    session_names, session_root_reasons = _session_file_names(session_root)
    input_paths = [
        batch_manifest_path,
        *(session_root / name for name in session_names),
    ]
    _refuse_collisions(input_paths, output_path, report_path)
    manifest_bytes = boundary.read_bytes(batch_manifest_path)
    manifest, manifest_reason = _parse_json_object(manifest_bytes)
    artifacts, decisions = _convert_documents(
        _ConversionInput(
            manifest_bytes=manifest_bytes,
            manifest=manifest,
            manifest_reason=manifest_reason,
            session_root=session_root,
            session_names=session_names,
            session_root_reasons=session_root_reasons,
            boundary=boundary,
        )
    )
    report = _build_report(decisions, manifest, sha256_bytes(manifest_bytes))
    newline = chr(10)
    _atomic_write_pair(
        output_path,
        _artifact_jsonl_bytes(artifacts),
        report_path,
        (canonical_dumps(report) + newline).encode("utf-8"),
    )
    return report

def _conversion_options(options: dict[str, Any]) -> tuple[tuple[Path, Path, Path, Path], Any]:
    paths = tuple(
        Path(options.pop(name))
        for name in ("batch_manifest_path", "session_root", "output_path", "report_path")
    )
    source = options.pop("source", None)
    if options:
        unexpected = ", ".join(sorted(options))
        raise TypeError(f"unexpected convert_files arguments: {unexpected}")
    if source is not None and not isinstance(source, LocalFileBoundary):
        raise TypeError("source must be a LocalFileBoundary")
    return paths, source

def _artifact_jsonl_bytes(artifacts: list[dict[str, Any]]) -> bytes:
    if not artifacts:
        return b""
    newline = chr(10)
    text = newline.join(canonical_dumps(artifact) for artifact in artifacts) + newline
    return text.encode("utf-8")

def _session_file_names(session_root: Path) -> tuple[list[str], list[str]]:
    try:
        if not session_root.is_dir():
            return [], ["missing_session_root"]
        names = sorted(
            path.name
            for path in session_root.glob("*.session.json")
            if path.is_file()
        )
    except OSError:
        return [], ["unreadable_session_root"]
    return names, []

def _convert_documents(
    source: _ConversionInput,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source.manifest is None:
        reason = source.manifest_reason or "invalid_batch_manifest"
        return [], [_refusal(reasons=[reason])]
    manifest = source.manifest
    batch_id = str(manifest.get("batch_id") or "")
    base_reasons = [
        *_manifest_errors(manifest),
        *_manifest_duplicate_errors(manifest),
        *source.session_root_reasons,
    ]
    context = _BatchContext(
        boundary=source.boundary,
        session_root=source.session_root,
        manifest=manifest,
        manifest_digest=sha256_bytes(source.manifest_bytes),
        batch_id=batch_id,
        base_reasons=base_reasons,
        raw_validator=_raw_validator(),
        artifact_validator=_artifact_validator(),
    )
    artifacts, decisions, referenced_files = _convert_envelope_list(manifest, context)
    decisions.extend(_orphan_refusals(source, context, referenced_files))
    if not decisions:
        decisions.append(
            _refusal(
                reasons=_unique_reasons([*base_reasons, "empty_input"]),
                batch_id=context.batch_id or None,
            )
        )
    return artifacts, decisions

def _convert_envelope_list(
    manifest: dict[str, Any], context: _BatchContext
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    artifacts: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    referenced_files: set[str] = set()
    envelopes = manifest.get("rights_envelopes")
    if not isinstance(envelopes, list):
        return artifacts, decisions, referenced_files
    for envelope in envelopes:
        artifact, decision = _convert_envelope(
            envelope,
            context=context,
            referenced_files=referenced_files,
        )
        decisions.append(decision)
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts, decisions, referenced_files

def _convert_envelope(
    envelope: Any,
    *,
    context: _BatchContext,
    referenced_files: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(envelope, dict) or _has_lone_surrogate(envelope):
        return None, _refusal(reasons=[*context.base_reasons, "invalid_rights_envelope"])
    decision_base = _envelope_decision_base(envelope, context)
    binding = _session_binding(envelope)
    session_file = decision_base["session_file"]
    if session_file is not None and _safe_session_file(session_file):
        referenced_files.add(session_file)
    reasons = [
        *context.base_reasons,
        *_envelope_errors(envelope),
        *_cross_bind_errors(envelope, context.manifest),
    ]
    if reasons:
        return None, _refusal(reasons=_unique_reasons(reasons), **decision_base)
    assert binding is not None
    return _convert_bound_session(
        binding,
        envelope=envelope,
        context=context,
        decision_base=decision_base,
    )

def _envelope_decision_base(
    envelope: dict[str, Any], context: _BatchContext
) -> dict[str, Any]:
    return {
        "batch_id": context.batch_id or None,
        "record_id": _optional_str(envelope.get("record_id")),
        "rights_envelope_sha256": _canonical_sha256(envelope),
        "session_file": _optional_str(envelope.get("session_file")),
        "session_id": None,
        "session_sha256": _optional_str(envelope.get("session_sha256")),
        "trajectory_id": None,
    }

def _convert_bound_session(
    binding: tuple[str, str],
    *,
    envelope: dict[str, Any],
    context: _BatchContext,
    decision_base: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    read = _read_session(context.boundary, context.session_root / binding[0])
    if read.reasons:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *read.reasons]),
            **decision_base,
        )
    assert read.payload is not None
    actual_session_sha256 = sha256_bytes(read.payload)
    decision_base["session_sha256"] = actual_session_sha256
    if actual_session_sha256 != binding[1]:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, "session_hash_mismatch"]),
            **decision_base,
        )
    return _convert_session_bytes(
        read.payload,
        envelope=envelope,
        context=context,
        decision_base=decision_base,
    )

def _convert_session_bytes(
    payload: bytes,
    *,
    envelope: dict[str, Any],
    context: _BatchContext,
    decision_base: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    parsed, parse_reason = _parse_json_object(payload)
    if parsed is None:
        return None, _refusal(
            reasons=_unique_reasons(
                [*context.base_reasons, parse_reason or "invalid_session_json"]
            ),
            **decision_base,
        )
    reasons = _raw_session_reasons(parsed, context)
    if reasons:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *reasons]),
            **decision_base,
        )
    decision_base = {**decision_base, "session_id": parsed.get("session_id")}
    return _convert_safe_session(
        parsed,
        envelope=envelope,
        context=context,
        decision_base=decision_base,
    )

def _raw_session_reasons(parsed: dict[str, Any], context: _BatchContext) -> list[str]:
    reasons = ["invalid_session_json"] if _has_lone_surrogate(parsed) else []
    reasons.extend(_raw_record_errors(parsed, context.raw_validator))
    reasons.extend(_tool_payload_reasons(parsed))
    reasons.extend(_safety_reasons(parsed, allow_hidden=True))
    return reasons

def _convert_safe_session(
    parsed: dict[str, Any],
    *,
    envelope: dict[str, Any],
    context: _BatchContext,
    decision_base: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        sanitized = strip_hidden_reasoning(sanitize_query_secrets(parsed))
    except UnsafeUrlError:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, "secret_leakage"]),
            **decision_base,
        )
    reasons = _safety_reasons(sanitized)
    if reasons:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *reasons]),
            **decision_base,
        )
    artifact = _build_artifact(sanitized, envelope, context)
    artifact_errors = _artifact_errors(artifact, context.artifact_validator)
    artifact_errors.extend(_safety_reasons(artifact))
    if artifact_errors:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *artifact_errors]),
            trajectory_id=artifact.get("id"),
            **{k: v for k, v in decision_base.items() if k != "trajectory_id"},
        )
    decision = {
        **decision_base,
        "status": "accepted",
        "reason_codes": [],
        "trajectory_id": artifact["id"],
    }
    return artifact, decision

def _read_session(boundary: LocalFileBoundary, path: Path) -> _SessionRead:
    try:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            return _SessionRead(payload=None, reasons=["unsafe_session_file"])
        return _SessionRead(payload=boundary.read_bytes(path), reasons=[])
    except FileNotFoundError:
        return _SessionRead(payload=None, reasons=["missing_session_file"])
    except (OSError, ValueError):
        return _SessionRead(payload=None, reasons=["unreadable_session_file"])

def _orphan_refusals(
    source: _ConversionInput,
    context: _BatchContext,
    referenced_files: set[str],
) -> list[dict[str, Any]]:
    return [
        _orphan_refusal(name, context)
        for name in source.session_names
        if name not in referenced_files
    ]

def _orphan_refusal(name: str, context: _BatchContext) -> dict[str, Any]:
    read = _read_session(context.boundary, context.session_root / name)
    session_sha256 = None
    session_id = None
    reasons = [*_unique_reasons(context.base_reasons), "missing_rights_envelope"]
    if read.payload is not None:
        session_sha256 = sha256_bytes(read.payload)
        parsed, _parse_reason = _parse_json_object(read.payload)
        if isinstance(parsed, dict) and not _safety_reasons(parsed, allow_hidden=True):
            session_id = parsed.get("session_id")
    else:
        reasons.extend(read.reasons)
    return _refusal(
        reasons=_unique_reasons(reasons),
        batch_id=context.batch_id or None,
        session_file=name,
        session_id=session_id,
        session_sha256=session_sha256,
    )

def _build_report(
    decisions: list[dict[str, Any]], manifest: dict[str, Any] | None, digest: str
) -> dict[str, Any]:
    batch_id = manifest.get("batch_id") if isinstance(manifest, dict) else None
    return {
        "accepted_count": sum(1 for row in decisions if row["status"] == "accepted"),
        "batch_id": batch_id if _nonempty_str(batch_id) else None,
        "batch_manifest_sha256": digest,
        "converter_version": CONVERTER_VERSION,
        "records": decisions,
        "refused_count": sum(1 for row in decisions if row["status"] == "refused"),
        "schema_version": REPORT_SCHEMA_VERSION,
    }
