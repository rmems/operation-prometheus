"""First-party Hermes artifact construction for medsynth conversion."""

from __future__ import annotations

import re
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

from validate_jsonl import load_schema

from .medsynth_hermes_common import (
    ARTIFACT_SCHEMA_PATH,
    ARTIFACT_SCHEMA_VERSION,
    CONVERTER_VERSION,
    _BatchContext,
    _canonical_sha256,
)


_ROUTE_TERMS_FIELDS = (
    "route_terms_document",
    "route_terms_version",
    "route_terms_date",
    "route_terms_url",
    "route_terms_clause",
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
