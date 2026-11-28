"""Fail-closed manifest and rights-envelope validation for medsynth conversion."""

from __future__ import annotations

from typing import Any

from .medsynth_hermes_common import (
    _is_sha256,
    _nonempty_str,
    _pin_entry_sha256,
    _unique_reasons,
)


_ENVELOPE_REQUIRED = (
    "record_id",
    "teacher_variant",
    "model_id",
    "route",
    "serving_vendor",
    "session_file",
    "session_sha256",
    "pin_id",
    "pin_entry",
    "pin_entry_sha256",
    "content_sha256",
)

_ENVELOPE_HASH_FIELDS = ("session_sha256", "pin_entry_sha256", "content_sha256")

_TEACHER_PIN_REQUIRED = (
    "pin_id",
    "variant",
    "model_id",
    "route",
    "pin_entry_sha256",
    "terms_document",
    "terms_version",
    "terms_date",
    "terms_url",
    "terms_clause",
    "snapshot_date",
)

def _manifest_errors(manifest: dict[str, Any]) -> list[str]:
    return _unique_reasons(
        [*_manifest_shape_errors(manifest), *_teacher_pin_errors(manifest.get("teacher_pin"))]
    )

def _manifest_shape_errors(manifest: dict[str, Any]) -> list[str]:
    invalid = any(
        (
            manifest.get("manifest_version") != 1,
            not _nonempty_str(manifest.get("batch_id")),
            not isinstance(manifest.get("rights_envelopes"), list),
        )
    )
    return ["invalid_batch_manifest"] if invalid else []

def _teacher_pin_errors(teacher_pin: Any) -> list[str]:
    if not isinstance(teacher_pin, dict):
        return ["incomplete_teacher_pin"]
    missing = [
        field
        for field in _TEACHER_PIN_REQUIRED
        if not _nonempty_str(teacher_pin.get(field))
    ]
    reasons = []
    if missing or not _is_sha256(teacher_pin.get("pin_entry_sha256")):
        reasons.append("incomplete_teacher_pin")
    route = str(teacher_pin.get("route") or "")
    if "hermes" not in route.casefold():
        reasons.append("teacher_route_not_hermes")
    return reasons

def _manifest_duplicate_errors(manifest: dict[str, Any]) -> list[str]:
    envelopes = manifest.get("rights_envelopes")
    if not isinstance(envelopes, list):
        return []
    keys = [key for envelope in envelopes for key in _envelope_identity_keys(envelope)]
    return ["duplicate_rights_envelope_binding"] if len(keys) != len(set(keys)) else []

def _envelope_identity_keys(envelope: Any) -> list[tuple[str, Any]]:
    if not isinstance(envelope, dict):
        return []
    keys = []
    record_id = envelope.get("record_id")
    if _nonempty_str(record_id):
        keys.append(("record", str(record_id)))
    binding = _session_binding(envelope)
    if binding is not None:
        keys.append(("session", binding))
    return keys

def _envelope_errors(envelope: dict[str, Any]) -> list[str]:
    return _unique_reasons(
        [
            *_envelope_shape_errors(envelope),
            *_pin_hash_errors(envelope),
            *_session_file_errors(envelope),
        ]
    )

def _envelope_shape_errors(envelope: dict[str, Any]) -> list[str]:
    missing = [
        field
        for field in _ENVELOPE_REQUIRED
        if not _nonempty_str(envelope.get(field))
    ]
    reasons = ["incomplete_rights_envelope"] if missing else []
    bad_hash = any(
        not _is_sha256(envelope.get(field)) for field in _ENVELOPE_HASH_FIELDS
    )
    served_model = envelope.get("served_model")
    bad_served_model = served_model is not None and not _nonempty_str(served_model)
    if bad_hash or bad_served_model:
        reasons.append("invalid_rights_envelope")
    return reasons

def _pin_hash_errors(envelope: dict[str, Any]) -> list[str]:
    pin_entry = envelope.get("pin_entry")
    pin_entry_sha256 = envelope.get("pin_entry_sha256")
    if not _nonempty_str(pin_entry) or not _is_sha256(pin_entry_sha256):
        return []
    mismatch = _pin_entry_sha256(str(pin_entry)) != pin_entry_sha256
    return ["pin_entry_hash_mismatch"] if mismatch else []

def _session_file_errors(envelope: dict[str, Any]) -> list[str]:
    session_file = envelope.get("session_file")
    if not _nonempty_str(session_file) or _safe_session_file(str(session_file)):
        return []
    return ["unsafe_session_file"]

def _cross_bind_errors(envelope: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    teacher_pin = manifest.get("teacher_pin")
    if not isinstance(teacher_pin, dict):
        return []
    comparisons = (
        ("pin_id", "pin_id"),
        ("teacher_variant", "variant"),
        ("model_id", "model_id"),
        ("route", "route"),
        ("pin_entry_sha256", "pin_entry_sha256"),
    )
    mismatched = any(
        _nonempty_str(envelope.get(envelope_field))
        and _nonempty_str(teacher_pin.get(pin_field))
        and envelope.get(envelope_field) != teacher_pin.get(pin_field)
        for envelope_field, pin_field in comparisons
    )
    return ["rights_envelope_mismatch"] if mismatched else []

def _session_binding(envelope: dict[str, Any]) -> tuple[str, str] | None:
    session_file = envelope.get("session_file")
    session_sha256 = envelope.get("session_sha256")
    if not _nonempty_str(session_file) or not _is_sha256(session_sha256):
        return None
    if not _safe_session_file(str(session_file)):
        return None
    return str(session_file), str(session_sha256)

def _safe_session_file(value: str) -> bool:
    return (
        value.endswith(".session.json")
        and not any(part in value for part in ("/", "\\", ":", "\x00"))
        and value not in {".", ".."}
    )
