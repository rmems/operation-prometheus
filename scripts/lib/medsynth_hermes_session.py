"""Bound-session reading and conversion for medsynth first-party artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hermes_binding import _raw_record_errors
from .hermes_json import _parse_json_object
from .hermes_normalize import LocalFileBoundary, sha256_bytes
from .hermes_safety import _safety_reasons, _tool_payload_reasons
from .hermes_sanitize import (
    UnsafeUrlError,
    sanitize_query_secrets,
    strip_hidden_reasoning,
)
from .medsynth_hermes_artifact import _build_artifact, _artifact_errors
from .medsynth_hermes_common import (
    _BatchContext,
    _SessionRead,
    _has_lone_surrogate,
    _refusal,
    _unique_reasons,
)


def _read_session(boundary: LocalFileBoundary, path: Path) -> _SessionRead:
    try:
        if path.is_symlink():
            return _SessionRead(payload=None, reasons=["unsafe_session_file"])
        if path.exists() and not path.is_file():
            return _SessionRead(payload=None, reasons=["unsafe_session_file"])
        return _SessionRead(payload=boundary.read_bytes(path), reasons=[])
    except FileNotFoundError:
        return _SessionRead(payload=None, reasons=["missing_session_file"])
    except (OSError, ValueError):
        return _SessionRead(payload=None, reasons=["unreadable_session_file"])

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
