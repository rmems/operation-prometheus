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

def _convert_envelope(
    envelope: Any,
    *,
    context: _BatchContext,
    referenced_files: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(envelope, dict):
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
        if path.is_symlink():
            return _SessionRead(payload=None, reasons=["unsafe_session_file"])
        return _SessionRead(payload=boundary.read_bytes(path), reasons=[])
    except FileNotFoundError:
        return _SessionRead(payload=None, reasons=["missing_session_file"])
    except (OSError, ValueError):
        return _SessionRead(payload=None, reasons=["unreadable_session_file"])


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
    event.update(_optional_event_fields(message))
    return event


def _optional_event_fields(message: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key in ("name", "timestamp")
        if isinstance((value := message.get(key)), str) and value
    }


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
