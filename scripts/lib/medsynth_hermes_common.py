"""Shared constants, context types, and small utilities for medsynth conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hermes_normalize import LocalFileBoundary, canonical_dumps, sha256_bytes


CONVERTER_VERSION = "medsynth-hermes-convert/0.1.0"

REPORT_SCHEMA_VERSION = "medsynth_hermes_convert_report_v1"

ARTIFACT_SCHEMA_VERSION = "first_party_hermes_trajectory_v1"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

ARTIFACT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "first_party_hermes_trajectory.schema.json"
)

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

@dataclass(frozen=True)
class _BatchContext:
    boundary: LocalFileBoundary
    session_root: Path
    manifest: dict[str, Any]
    manifest_digest: str
    batch_id: str
    base_reasons: list[str]
    raw_validator: Any
    artifact_validator: Any

@dataclass(frozen=True)
class _ConversionInput:
    manifest_bytes: bytes
    manifest: dict[str, Any] | None
    manifest_reason: str
    session_root: Path
    session_names: list[str]
    session_root_reasons: list[str]
    boundary: LocalFileBoundary

@dataclass(frozen=True)
class _SessionRead:
    payload: bytes | None
    reasons: list[str]

def _canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))

def _has_lone_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    if isinstance(value, list):
        return any(_has_lone_surrogate(item) for item in value)
    if isinstance(value, dict):
        return any(
            _has_lone_surrogate(key) or _has_lone_surrogate(item)
            for key, item in value.items()
        )
    return False

def _pin_entry_sha256(pin_entry: str) -> str:
    canonical = pin_entry.replace("\r\n", "\n").replace("\r", "\n").strip()
    return sha256_bytes(canonical.encode("utf-8"))

def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None

def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _optional_str(value: Any) -> str | None:
    return value if _nonempty_str(value) else None

def _unique_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reason for reason in reasons if reason))

def _refusal(*, reasons: list[str], **fields: Any) -> dict[str, Any]:
    allowed = {
        "batch_id",
        "record_id",
        "rights_envelope_sha256",
        "session_file",
        "session_id",
        "session_sha256",
        "trajectory_id",
    }
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise TypeError(f"unexpected refusal fields: {', '.join(unknown)}")
    session_id = fields.get("session_id")
    return {
        "batch_id": fields.get("batch_id"),
        "record_id": fields.get("record_id"),
        "reason_codes": _unique_reasons(reasons),
        "rights_envelope_sha256": fields.get("rights_envelope_sha256"),
        "session_file": fields.get("session_file"),
        "session_id": session_id if _nonempty_str(session_id) else None,
        "session_sha256": fields.get("session_sha256"),
        "status": "refused",
        "trajectory_id": fields.get("trajectory_id"),
    }
