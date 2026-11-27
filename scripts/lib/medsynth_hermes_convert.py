"""Convert medsynth Hermes session records into first-party artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised at CLI startup
    jsonschema = None

from validate_jsonl import load_schema

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

CONVERTER_VERSION = "medsynth-hermes-convert/0.1.0"
REPORT_SCHEMA_VERSION = "medsynth_hermes_convert_report_v1"
ARTIFACT_SCHEMA_VERSION = "first_party_hermes_trajectory_v1"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "first_party_hermes_trajectory.schema.json"
)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

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
_ROUTE_TERMS_FIELDS = (
    "route_terms_document",
    "route_terms_version",
    "route_terms_date",
    "route_terms_url",
    "route_terms_clause",
)


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


def convert_files(**options: Any) -> dict[str, Any]:
    """Convert all Hermes sessions bound by one medsynth batch manifest."""
    batch_manifest_path = Path(options.pop("batch_manifest_path"))
    session_root = Path(options.pop("session_root"))
    output_path = Path(options.pop("output_path"))
    report_path = Path(options.pop("report_path"))
    source = options.pop("source", None)
    if options:
        unexpected = ", ".join(sorted(options))
        raise TypeError(f"unexpected convert_files arguments: {unexpected}")
    if source is not None and not isinstance(source, LocalFileBoundary):
        raise TypeError("source must be a LocalFileBoundary")
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
    admitted = [canonical_dumps(artifact) for artifact in artifacts]
    output_text = ("\n".join(admitted) + "\n") if admitted else ""
    report = _build_report(decisions, manifest, sha256_bytes(manifest_bytes))
    _atomic_write_pair(
        output_path,
        output_text.encode("utf-8"),
        report_path,
        (canonical_dumps(report) + "\n").encode("utf-8"),
    )
    return report


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
    artifacts: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    referenced_files: set[str] = set()
    seen_record_ids: set[str] = set()
    seen_session_bindings: set[tuple[str, str]] = set()
    envelopes = manifest.get("rights_envelopes")
    if isinstance(envelopes, list):
        for envelope in envelopes:
            artifact, decision = _convert_envelope(
                envelope,
                context=context,
                referenced_files=referenced_files,
                seen_record_ids=seen_record_ids,
                seen_session_bindings=seen_session_bindings,
            )
            decisions.append(decision)
            if artifact is not None:
                artifacts.append(artifact)
    decisions.extend(_orphan_refusals(source, context, referenced_files))
    if not decisions:
        decisions.append(
            _refusal(
                reasons=_unique_reasons([*base_reasons, "empty_input"]),
                batch_id=context.batch_id or None,
            )
        )
    return artifacts, decisions


def _manifest_errors(manifest: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if manifest.get("manifest_version") != 1:
        reasons.append("invalid_batch_manifest")
    if not _nonempty_str(manifest.get("batch_id")):
        reasons.append("invalid_batch_manifest")
    if not isinstance(manifest.get("rights_envelopes"), list):
        reasons.append("invalid_batch_manifest")
    teacher_pin = manifest.get("teacher_pin")
    if not isinstance(teacher_pin, dict):
        reasons.append("incomplete_teacher_pin")
    else:
        missing = [
            field
            for field in _TEACHER_PIN_REQUIRED
            if not _nonempty_str(teacher_pin.get(field))
        ]
        if missing or not _is_sha256(teacher_pin.get("pin_entry_sha256")):
            reasons.append("incomplete_teacher_pin")
        route = str(teacher_pin.get("route") or "")
        if "hermes" not in route.casefold():
            reasons.append("teacher_route_not_hermes")
    return _unique_reasons(reasons)


def _manifest_duplicate_errors(manifest: dict[str, Any]) -> list[str]:
    envelopes = manifest.get("rights_envelopes")
    if not isinstance(envelopes, list):
        return []
    record_ids: set[str] = set()
    bindings: set[tuple[str, str]] = set()
    duplicate = False
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            continue
        record_id = envelope.get("record_id")
        if _nonempty_str(record_id):
            duplicate = duplicate or str(record_id) in record_ids
            record_ids.add(str(record_id))
        binding = _session_binding(envelope)
        if binding is not None:
            duplicate = duplicate or binding in bindings
            bindings.add(binding)
    return ["duplicate_rights_envelope_binding"] if duplicate else []


def _convert_envelope(
    envelope: Any,
    *,
    context: _BatchContext,
    referenced_files: set[str],
    seen_record_ids: set[str],
    seen_session_bindings: set[tuple[str, str]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(envelope, dict):
        return None, _refusal(reasons=[*context.base_reasons, "invalid_rights_envelope"])
    envelope_digest = _canonical_sha256(envelope)
    record_id = _optional_str(envelope.get("record_id"))
    session_file = _optional_str(envelope.get("session_file"))
    reasons = [*_envelope_errors(envelope), *_cross_bind_errors(envelope, context.manifest)]
    reasons.extend(_duplicate_reasons(envelope, seen_record_ids, seen_session_bindings))
    if record_id:
        seen_record_ids.add(record_id)
    binding = _session_binding(envelope)
    if session_file is not None and _safe_session_file(session_file):
        referenced_files.add(session_file)
    if binding is not None:
        seen_session_bindings.add(binding)
    decision_base = {
        "batch_id": context.batch_id or None,
        "record_id": record_id,
        "rights_envelope_sha256": envelope_digest,
        "session_file": session_file,
        "session_id": None,
        "session_sha256": _optional_str(envelope.get("session_sha256")),
        "trajectory_id": None,
    }
    if context.base_reasons or reasons:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *reasons]),
            **decision_base,
        )
    assert binding is not None
    session_path = context.session_root / binding[0]
    read = _read_session(context.boundary, session_path)
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
    reasons = ["invalid_session_json"] if _has_lone_surrogate(parsed) else []
    reasons.extend(_raw_record_errors(parsed, context.raw_validator))
    reasons.extend(_tool_payload_reasons(parsed))
    reasons.extend(_safety_reasons(parsed, allow_hidden=True))
    if reasons:
        return None, _refusal(
            reasons=_unique_reasons([*context.base_reasons, *reasons]),
            **decision_base,
        )
    decision_base = {**decision_base, "session_id": parsed.get("session_id")}
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
        if path.is_symlink():
            return _SessionRead(payload=None, reasons=["unsafe_session_file"])
        return _SessionRead(payload=boundary.read_bytes(path), reasons=[])
    except FileNotFoundError:
        return _SessionRead(payload=None, reasons=["missing_session_file"])
    except (OSError, ValueError):
        return _SessionRead(payload=None, reasons=["unreadable_session_file"])


def _envelope_errors(envelope: dict[str, Any]) -> list[str]:
    missing = [
        field
        for field in _ENVELOPE_REQUIRED
        if not _nonempty_str(envelope.get(field))
    ]
    reasons = ["incomplete_rights_envelope"] if missing else []
    if any(not _is_sha256(envelope.get(field)) for field in _ENVELOPE_HASH_FIELDS):
        reasons.append("invalid_rights_envelope")
    served_model = envelope.get("served_model")
    if served_model is not None and not _nonempty_str(served_model):
        reasons.append("invalid_rights_envelope")
    pin_entry = envelope.get("pin_entry")
    pin_entry_sha256 = envelope.get("pin_entry_sha256")
    if (
        _nonempty_str(pin_entry)
        and _is_sha256(pin_entry_sha256)
        and _pin_entry_sha256(str(pin_entry)) != pin_entry_sha256
    ):
        reasons.append("pin_entry_hash_mismatch")
    session_file = envelope.get("session_file")
    if _nonempty_str(session_file) and not _safe_session_file(str(session_file)):
        reasons.append("unsafe_session_file")
    return _unique_reasons(reasons)


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


def _duplicate_reasons(
    envelope: dict[str, Any],
    seen_record_ids: set[str],
    seen_session_bindings: set[tuple[str, str]],
) -> list[str]:
    reasons: list[str] = []
    record_id = envelope.get("record_id")
    if _nonempty_str(record_id) and str(record_id) in seen_record_ids:
        reasons.append("duplicate_record_id")
    binding = _session_binding(envelope)
    if binding is not None and binding in seen_session_bindings:
        reasons.append("duplicate_session_binding")
    return reasons


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


def _build_artifact(
    session: dict[str, Any], envelope: dict[str, Any], context: _BatchContext
) -> dict[str, Any]:
    teacher_pin = context.manifest.get("teacher_pin")
    assert isinstance(teacher_pin, dict)
    events = _trace_events(session.get("messages"))
    pin_entry = str(envelope["pin_entry"])
    rights = {
        "pin_entry": pin_entry,
        "pin_entry_sha256": envelope["pin_entry_sha256"],
        "snapshot_date": teacher_pin["snapshot_date"],
        "terms_clause": teacher_pin["terms_clause"],
        "terms_date": teacher_pin["terms_date"],
        "terms_document": teacher_pin["terms_document"],
        "terms_url": teacher_pin["terms_url"],
        "terms_version": teacher_pin["terms_version"],
        **_route_terms(pin_entry),
    }
    artifact = {
        "artifact_kind": "hermes_session_trajectory",
        "collector_version": CONVERTER_VERSION,
        "id": _artifact_id(context.batch_id, envelope, session),
        "license": teacher_pin["terms_document"],
        "rights": rights,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "session": {
            "completed": session["completed"],
            "partial": session["partial"],
            "raw_trace_id": session["raw_trace_id"],
            "run_id": session["run_id"],
            "session_file": envelope["session_file"],
            "session_id": session["session_id"],
            "session_sha256": envelope["session_sha256"],
            "task_id": session["task_id"],
            **_optional_timestamps(session),
        },
        "source": {
            "batch_id": context.batch_id,
            "batch_manifest_sha256": context.manifest_digest,
            "producer_repo": "rmems/medsynth",
            "record_id": envelope["record_id"],
            "rights_envelope_sha256": _canonical_sha256(envelope),
            "type": "first_party",
        },
        "teacher": {
            "model_id": envelope["model_id"],
            "pin_entry_sha256": envelope["pin_entry_sha256"],
            "pin_id": envelope["pin_id"],
            "route": envelope["route"],
            "served_model": envelope.get("served_model"),
            "serving_vendor": envelope["serving_vendor"],
            "variant": envelope["teacher_variant"],
        },
        "trace": {"event_count": len(events), "events": events},
    }
    return artifact


def _trace_events(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    final_assistant = max(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "assistant"
        ),
        default=-1,
    )
    return [
        _trace_event(message, index, final_assistant)
        for index, message in enumerate(messages)
    ]


def _trace_event(message: Any, index: int, final_assistant: int) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ValueError("non-object message")
    role = str(message.get("role") or "")
    event = {
        "content": str(message.get("content") or ""),
        "event_id": f"e{index + 1}",
        "kind": _event_kind(role, index, final_assistant),
        "ordinal": index + 1,
        "role": role,
    }
    name = message.get("name")
    if isinstance(name, str) and name:
        event["name"] = name
    timestamp = message.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        event["timestamp"] = timestamp
    return event


def _event_kind(role: str, index: int, final_assistant: int) -> str:
    if role in {"system", "user"}:
        return "prompt"
    if role == "tool":
        return "tool_event"
    if role == "assistant":
        return "output" if index == final_assistant else "decision"
    return "other"


def _optional_timestamps(session: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("started_at", "ended_at"):
        value = session.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    return out


def _route_terms(pin_entry: str) -> dict[str, str]:
    return {
        field: value
        for field in _ROUTE_TERMS_FIELDS
        if (value := _pin_entry_field(pin_entry, field)) is not None
    }


def _pin_entry_field(pin_entry: str, field: str) -> str | None:
    pattern = rf"^- \*\*{re.escape(field)}:\*\* `([^`]+)`"
    match = re.search(pattern, pin_entry, flags=re.MULTILINE)
    return match.group(1) if match else None


def _artifact_id(
    batch_id: str, envelope: dict[str, Any], session: dict[str, Any]
) -> str:
    parts = (
        batch_id,
        str(envelope["record_id"]),
        str(session["run_id"]),
        str(session["session_id"]),
        str(session["task_id"]),
        str(session["raw_trace_id"]),
    )
    encoded = "/".join(f"{len(part)}:{part}" for part in parts)
    return f"medsynth-hermes:{encoded}"


def _artifact_errors(artifact: dict[str, Any], validator: Any) -> list[str]:
    if validator is None:
        return ["jsonschema_missing"]
    errors = sorted(validator.iter_errors(artifact), key=lambda item: list(item.path))
    return ["invalid_artifact"] if errors else []


def _artifact_validator() -> Any:
    if jsonschema is None:
        return None
    return jsonschema.Draft7Validator(
        load_schema(ARTIFACT_SCHEMA_PATH),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _orphan_refusals(
    source: _ConversionInput,
    context: _BatchContext,
    referenced_files: set[str],
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for name in source.session_names:
        if name in referenced_files:
            continue
        read = _read_session(context.boundary, context.session_root / name)
        session_id = None
        session_sha256 = None
        reasons = [*_unique_reasons(context.base_reasons), "missing_rights_envelope"]
        if read.payload is not None:
            session_sha256 = sha256_bytes(read.payload)
            parsed, _parse_reason = _parse_json_object(read.payload)
            if isinstance(parsed, dict):
                session_id = parsed.get("session_id")
        else:
            reasons.extend(read.reasons)
        decisions.append(
            _refusal(
                reasons=_unique_reasons(reasons),
                batch_id=context.batch_id or None,
                session_file=name,
                session_id=session_id,
                session_sha256=session_sha256,
            )
        )
    return decisions


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


def _refusal(
    *,
    reasons: list[str],
    batch_id: str | None = None,
    record_id: str | None = None,
    rights_envelope_sha256: str | None = None,
    session_file: str | None = None,
    session_id: Any = None,
    session_sha256: str | None = None,
    trajectory_id: str | None = None,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "record_id": record_id,
        "reason_codes": _unique_reasons(reasons),
        "rights_envelope_sha256": rights_envelope_sha256,
        "session_file": session_file,
        "session_id": session_id if _nonempty_str(session_id) else None,
        "session_sha256": session_sha256,
        "status": "refused",
        "trajectory_id": trajectory_id,
    }


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
