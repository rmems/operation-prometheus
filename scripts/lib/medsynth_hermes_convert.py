"""Convert medsynth Hermes session records into first-party artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hermes_binding import _raw_validator
from .hermes_json import _parse_json_object
from .hermes_normalize import (
    LocalFileBoundary,
    _atomic_write_pair,
    _refuse_collisions,
    canonical_dumps,
    sha256_bytes,
)
from .medsynth_hermes_artifact import (
    _artifact_validator,
)
from .medsynth_hermes_common import (
    _BatchContext,
    _ConversionInput,
    _canonical_sha256,
    _has_lone_surrogate,
    _optional_str,
    _refusal,
    _unique_reasons,
)
from .medsynth_hermes_common import _build_report
from .medsynth_hermes_session import (
    _convert_bound_session,
    _orphan_refusals,
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
    if not isinstance(envelope, dict):
        return None, _refusal(reasons=[*context.base_reasons, "invalid_rights_envelope"])
    if _has_lone_surrogate(envelope):
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


