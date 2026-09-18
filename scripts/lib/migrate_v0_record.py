"""Single-record v0-to-v1 migration decisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from validate_jsonl import policy_errors

from .migrate_v0_contract import v0_contract_reason
from .migrate_v0_envelope import MappingContext, candidate_envelope
from .migrate_v0_events import unknown_event_reason
from .migrate_v0_fields import collect_unavailable, extract_code_state, extract_timestamp, nonempty_str
from .migrate_v0_text import is_v1_schema_version, parse_json_object, source_digest, v1_validator


@dataclass(frozen=True)
class SourceMeta:
    digest: str
    byte_size: int
    source_text: str
    source_bytes: bytes


@dataclass(frozen=True)
class Refusal:
    reasons: list[str]
    detail: str
    unavailable: list[str] | None = None
    trajectory_id: str | None = None


def migrate_record(
    line_bytes: bytes,
    *,
    validator: Any | None = None,
) -> dict[str, Any]:
    """Migrate one JSONL line. Returns an admitted/refused decision dict."""
    parsed, meta, refusal = _load_record(line_bytes)
    if refusal is not None:
        return refusal
    refusal = _refuse_ineligible(parsed, meta)
    if refusal is not None:
        return refusal
    return _admit(parsed, meta, validator)


def _load_record(
    line_bytes: bytes,
) -> tuple[dict[str, Any] | None, SourceMeta | None, dict[str, Any] | None]:
    try:
        digest, byte_size, source_text = source_digest(line_bytes)
    except UnicodeDecodeError:
        return None, None, _utf8_refusal(line_bytes)
    parsed, reason, detail = parse_json_object(source_text)
    meta = SourceMeta(digest, byte_size, source_text, line_bytes.rstrip(b"\r\n"))
    if parsed is None:
        return None, None, _refusal(meta, Refusal([reason], detail))
    return parsed, meta, None


def _utf8_refusal(line_bytes: bytes) -> dict[str, Any]:
    payload = line_bytes.rstrip(b"\r\n")
    meta = SourceMeta(hashlib.sha256(payload).hexdigest(), len(payload), "", payload)
    return _refusal(meta, Refusal(["invalid_utf8"], "source record is not valid UTF-8"))


def _refuse_ineligible(parsed: dict[str, Any], meta: SourceMeta) -> dict[str, Any] | None:
    return (
        _refuse_already_v1(parsed, meta)
        or _refuse_reason(
            parsed,
            meta,
            v0_contract_reason,
            "source does not satisfy the v0 contract plus documented extensions",
        )
        or _refuse_reason(
            parsed,
            meta,
            unknown_event_reason,
            "source contains an event or validation type that was not in the v0 contract",
        )
        or _refuse_timestamp(parsed, meta)
        or _refuse_code_state(parsed, meta)
    )


def _refuse_already_v1(parsed: dict[str, Any], meta: SourceMeta) -> dict[str, Any] | None:
    if not is_v1_schema_version(parsed.get("schema_version")):
        return None
    return _refusal(
        meta,
        Refusal(
            ["already_v1"],
            (
                "already-v1 input is refused (documented no-op: the source is "
                "left unchanged and is not copied to the migrated output)"
            ),
            trajectory_id=nonempty_str(parsed.get("trajectory_id")),
        ),
    )


def _refuse_reason(
    parsed: dict[str, Any],
    meta: SourceMeta,
    checker: Any,
    detail: str,
) -> dict[str, Any] | None:
    reason = checker(parsed)
    if reason is None:
        return None
    return _record_refusal(parsed, meta, [reason], detail)


def _refuse_timestamp(parsed: dict[str, Any], meta: SourceMeta) -> dict[str, Any] | None:
    _timestamp, ts_error = extract_timestamp(parsed)
    if ts_error is None:
        return None
    detail = (
        "source timestamp is not a parseable UTC instant"
        if ts_error == "malformed_timestamp"
        else "source has no timestamp; refusing rather than fabricating one"
    )
    return _record_refusal(parsed, meta, [ts_error], detail)


def _refuse_code_state(parsed: dict[str, Any], meta: SourceMeta) -> dict[str, Any] | None:
    code_state, oid_error = extract_code_state(parsed)
    if oid_error is not None:
        return _record_refusal(
            parsed,
            meta,
            [oid_error],
            "source commit OID is present but is not a git object id"
            if oid_error == "malformed_commit_oid"
            else "source maps the same code-state field to conflicting OIDs",
        )
    if code_state:
        return None
    return _record_refusal(
        parsed,
        meta,
        ["unavailable_commit_oid"],
        (
            "software v1 strict-policy requires a code-state OID; source "
            "has none and the migrator will not invent one"
        ),
    )


def _admit(parsed: dict[str, Any], meta: SourceMeta, validator: Any | None) -> dict[str, Any]:
    unavailable = collect_unavailable(parsed)
    timestamp, _ts_error = extract_timestamp(parsed)
    code_state, _oid_error = extract_code_state(parsed)
    built = candidate_envelope(
        MappingContext(
            record=parsed,
            source_text=meta.source_text,
            source_bytes=meta.source_bytes,
            digest=meta.digest,
            timestamp=timestamp or "",
            code_state=code_state,
            unavailable=unavailable,
        )
    )
    if isinstance(built, str):
        return _refusal(
            meta,
            Refusal(
                [built],
                f"lossless mapping refused: {built}",
                unavailable=unavailable,
                trajectory_id=nonempty_str(parsed.get("id")),
            ),
        )
    return _schema_gate(built, meta, unavailable, validator)


def _schema_gate(
    built: dict[str, Any],
    meta: SourceMeta,
    unavailable: list[str],
    validator: Any | None,
) -> dict[str, Any]:
    active = validator if validator is not None else v1_validator()
    schema_errors = [
        error.message for error in sorted(active.iter_errors(built), key=lambda item: list(item.path))
    ]
    policy = policy_errors(built, 1, "migrated")
    if not schema_errors and not policy:
        return {
            "status": "admitted",
            "source_sha256": meta.digest,
            "source_byte_size": meta.byte_size,
            "reason_codes": [],
            "unavailable_fields": unavailable,
            "trajectory_id": built["trajectory_id"],
            "detail": "",
            "output_record": built,
        }
    reasons = []
    if schema_errors:
        reasons.append("v1_schema")
    if policy:
        reasons.append("strict_policy")
    return _refusal(
        meta,
        Refusal(
            reasons,
            "; ".join(schema_errors + policy),
            unavailable=unavailable,
            trajectory_id=nonempty_str(built.get("trajectory_id")),
        ),
    )


def _record_refusal(
    parsed: dict[str, Any],
    meta: SourceMeta,
    reasons: list[str],
    detail: str,
) -> dict[str, Any]:
    return _refusal(
        meta,
        Refusal(
            reasons,
            detail,
            unavailable=collect_unavailable(parsed),
            trajectory_id=nonempty_str(parsed.get("id")),
        ),
    )


def _refusal(meta: SourceMeta, spec: Refusal) -> dict[str, Any]:
    return {
        "status": "refused",
        "source_sha256": meta.digest,
        "source_byte_size": meta.byte_size,
        "reason_codes": spec.reasons,
        "unavailable_fields": list(spec.unavailable or []),
        "trajectory_id": spec.trajectory_id,
        "detail": spec.detail,
        "output_record": None,
    }
