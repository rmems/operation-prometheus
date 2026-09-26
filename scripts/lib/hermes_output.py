"""Build and verify emitted Hermes trajectory records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .hermes_sanitize import sanitize_query_secrets

NORMALIZER_VERSION = "hermes-normalize/0.1.0"
SCHEMA_VERSION = "1.1"
COLLECTION_POLICY = "isolated-local-hermes"
PROVIDER_ID = "hermes-agent"
ALLOWED_OLLAMA_CONFIG = frozenset({"num_ctx", "keep_alive"})
_REPO_FIELDS = ("owner", "name", "url", "base_oid", "head_oid")
_WORKSPACE_FIELDS = ("id", "kind")
_VERIFIER_FIELDS = ("identity", "version", "outcome")
_SUCCESS_OUTCOMES = frozenset(
    {"pass", "passed", "success", "successful", "verified", "ok"}
)
_FAILED_OUTCOMES = frozenset({"fail", "failed", "error", "falsified"})
_INTERRUPTED_OUTCOMES = frozenset({"interrupted", "timeout", "killed", "incomplete"})
_TERMINAL_EVIDENCE = frozenset({"successful", "failed", "interrupted"})
_ACTOR_TYPES = {
    "user": "human",
    "human": "human",
    "assistant": "agent",
    "agent": "agent",
    "tool": "application",
    "application": "application",
    "system": "application",
}
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class _EmissionContext:
    input_digest: str
    manifest_digest: str
    admission_digest: str
    raw_trace_sha256: str
    terminal: str


@dataclass(frozen=True)
class _EventData:
    event_id: str
    timestamp: str
    actor_type: str
    event_type: str
    disposition: str
    content: str = ""


@dataclass(frozen=True)
class _EventContext:
    repository: dict[str, Any]
    started_at: str
    terminal: str
    last_index: int


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity_tuple(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record["run_id"]),
        str(record["session_id"]),
        str(record["task_id"]),
        str(record["raw_trace_id"]),
    )


def _trajectory_id(record: dict[str, Any]) -> str:
    encoded = "/".join(f"{len(part)}:{part}" for part in _identity_tuple(record))
    return f"hermes:{encoded}"


def _mapping_conflicts(
    trace_obj: Any, manifest_obj: Any, fields: tuple[str, ...], reason: str
) -> list[str]:
    if not isinstance(trace_obj, dict):
        return []
    if not isinstance(manifest_obj, dict):
        return [reason]
    for field in fields:
        if field in trace_obj and trace_obj.get(field) != manifest_obj.get(field):
            return [reason]
    return []


def _trace_conflicts(record: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reasons.extend(
        _mapping_conflicts(
            record.get("repository"),
            manifest.get("repository"),
            _REPO_FIELDS,
            "repository_conflict",
        )
    )
    reasons.extend(
        _mapping_conflicts(
            record.get("workspace"),
            manifest.get("workspace"),
            _WORKSPACE_FIELDS,
            "workspace_conflict",
        )
    )
    source = record.get("verifier")
    expected = (
        manifest.get("verifier") if isinstance(manifest.get("verifier"), dict) else {}
    )
    if isinstance(source, dict):
        for field in _VERIFIER_FIELDS:
            if field in source and source.get(field) != expected.get(field):
                reasons.append("verifier_conflict")
                break
        else:
            hashes = _artifact_hashes(expected.get("artifacts"))
            if "artifact_sha256" in source and source.get("artifact_sha256") != hashes:
                reasons.append("verifier_conflict")
    elif source is not None:
        reasons.append("verifier_conflict")
    return reasons


def _artifact_hashes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    hashes: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            return []
        content = item.get("content")
        digest = item.get("sha256")
        if not isinstance(content, str) or not _is_sha256(digest):
            return []
        if sha256_bytes(content.encode("utf-8")) != digest:
            return []
        hashes.append(digest)
    return hashes


def _independent_terminal(
    manifest: dict[str, Any], record: dict[str, Any]
) -> tuple[str | None, list[str]]:
    verifier = manifest.get("verifier")
    if not isinstance(verifier, dict):
        return None, ["verifier_evidence"]
    terminal = _verified_terminal(verifier.get("outcome"))
    if terminal not in _TERMINAL_EVIDENCE:
        return None, []
    return terminal, _verifier_evidence_errors(verifier, manifest, record)


def _verified_terminal(outcome: Any) -> str | None:
    if outcome is None or outcome == "":
        return None
    return _terminal_disposition(str(outcome).strip().lower())


def _verifier_evidence_errors(
    verifier: dict[str, Any], manifest: dict[str, Any], record: dict[str, Any]
) -> list[str]:
    expected_subject = dict(
        zip(
            ("run_id", "session_id", "task_id", "raw_trace_id"), _identity_tuple(record)
        )
    )
    if verifier.get("subject") != expected_subject:
        return ["verifier_subject_mismatch"]
    valid = (
        _nonempty_str(verifier.get("identity"))
        and _nonempty_str(verifier.get("version"))
        and _external_verifier_identity(
            str(verifier.get("identity")), _producer_name(manifest)
        )
        and bool(_artifact_hashes(verifier.get("artifacts")))
    )
    return [] if valid else ["verifier_evidence"]


def _producer_name(manifest: dict[str, Any]) -> str:
    producer = manifest.get("producer")
    if not isinstance(producer, dict):
        return ""
    return str(producer.get("name") or "")


def _external_verifier_identity(identity: str, producer: str) -> bool:
    folded = identity.casefold()
    blocked = {producer.casefold(), PROVIDER_ID.casefold(), "hermes-agent"}
    return folded not in blocked


def _terminal_disposition(outcome: str | None) -> str | None:
    if outcome is None:
        return None
    if outcome in _SUCCESS_OUTCOMES:
        return "successful"
    if outcome in _FAILED_OUTCOMES:
        return "failed"
    if outcome in _INTERRUPTED_OUTCOMES:
        return "interrupted"
    return None


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in fields:
        if field in source:
            out[field] = source[field]
    return out


def _ollama_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    source = manifest.get("ollama") if isinstance(manifest.get("ollama"), dict) else {}
    out: dict[str, Any] = {
        "endpoint": sanitize_query_secrets(str(source.get("endpoint") or "")),
        "runtime": source.get("runtime"),
        "version": source.get("version"),
    }
    config = source.get("config")
    if isinstance(config, dict):
        cleaned = {
            key: value for key, value in config.items() if key in ALLOWED_OLLAMA_CONFIG
        }
        if cleaned:
            out["config"] = cleaned
    return out


def _verifier_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    source = (
        manifest.get("verifier") if isinstance(manifest.get("verifier"), dict) else {}
    )
    return {
        "artifact_sha256": _artifact_hashes(source.get("artifacts")),
        "identity": source.get("identity"),
        "outcome": source.get("outcome"),
        "version": source.get("version"),
    }


def _repository_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    source = (
        manifest.get("repository")
        if isinstance(manifest.get("repository"), dict)
        else {}
    )
    out = _pick(source, _REPO_FIELDS)
    cleaned = {key: value for key, value in out.items() if value not in (None, "")}
    url = cleaned.get("url")
    if isinstance(url, str) and url:
        cleaned["url"] = sanitize_query_secrets(url)
    return cleaned


def _workspace_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    source = (
        manifest.get("workspace") if isinstance(manifest.get("workspace"), dict) else {}
    )
    return _pick(source, _WORKSPACE_FIELDS)


def _emit_record(
    record: dict[str, Any],
    *,
    manifest: dict[str, Any],
    context: _EmissionContext,
) -> dict[str, Any]:
    repository = _repository_from_manifest(manifest)
    workspace = _workspace_from_manifest(manifest)
    producer = _pick(
        manifest.get("producer") if isinstance(manifest.get("producer"), dict) else {},
        ("name", "profile", "version", "revision"),
    )
    model = _pick(
        manifest.get("model") if isinstance(manifest.get("model"), dict) else {},
        ("name", "tag", "ollama_digest", "quantization", "upstream_revision"),
    )
    retention = _pick(
        manifest.get("reasoning_retention")
        if isinstance(manifest.get("reasoning_retention"), dict)
        else {},
        ("policy", "strip_tags"),
    )
    events = _events(record, repository, context.terminal)
    payload = _software_payload(record, context.terminal)
    run_id, session_id, task_id, raw_trace_id = _identity_tuple(record)
    return {
        "artifacts": [],
        "collection_policy": COLLECTION_POLICY,
        "collector_version": NORMALIZER_VERSION,
        "events": events,
        "execution": {
            "producer_completed": record["completed"],
            "producer_partial": record["partial"],
        },
        "execution_provenance": {
            "admission_report_sha256": context.admission_digest,
            "input_sha256": context.input_digest,
            "model": model,
            "ollama": _ollama_from_manifest(manifest),
            "producer": producer,
            "raw_trace_id": raw_trace_id,
            "raw_trace_sha256": context.raw_trace_sha256,
            "repository": repository,
            "reasoning_retention": retention,
            "run_id": run_id,
            "run_manifest_sha256": context.manifest_digest,
            "session_id": session_id,
            "task_id": task_id,
            "verifier": _verifier_from_manifest(manifest),
            "workspace": workspace,
        },
        "license": manifest["output_license"],
        "provider_id": PROVIDER_ID,
        "repository": repository,
        "schema_version": SCHEMA_VERSION,
        "software_payload": payload,
        "source_id": raw_trace_id,
        "terminal_disposition": context.terminal,
        "trajectory_id": _trajectory_id(record),
        "trajectory_type": "software",
    }


def _events(
    record: dict[str, Any], repository: dict[str, Any], terminal: str
) -> list[dict[str, Any]]:
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        timestamp = str(record.get("started_at") or record.get("ended_at") or "")
        return [
            _event(_EventData("e1", timestamp, "agent", "run", terminal), repository)
        ]
    context = _EventContext(
        repository=repository,
        started_at=str(record.get("started_at") or ""),
        terminal=terminal,
        last_index=len(messages) - 1,
    )
    return [
        _message_event(message, index, context)
        for index, message in enumerate(messages)
    ]


def _message_event(message: Any, index: int, context: _EventContext) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ValueError("non-object message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("non-string message content")
    role = str(message.get("role") or "assistant")
    data = _EventData(
        event_id=f"e{index + 1}",
        timestamp=str(message.get("timestamp") or context.started_at),
        actor_type=_ACTOR_TYPES.get(role, "agent"),
        event_type="tool_call" if role == "tool" else "message",
        disposition=context.terminal if index == context.last_index else "neutral",
        content=content,
    )
    return _event(data, context.repository)


def _event(data: _EventData, repository: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "actor": {
            "id": PROVIDER_ID if data.actor_type != "human" else "user",
            "type": data.actor_type,
        },
        "code_state": {
            "base_oid": repository.get("base_oid"),
            "head_oid": repository.get("head_oid"),
        },
        "disposition": data.disposition,
        "event_id": data.event_id,
        "event_type": data.event_type,
        "timestamp": data.timestamp,
    }
    if data.content:
        event["content"] = data.content
    url = repository.get("url")
    if isinstance(url, str) and url:
        event["evidence_references"] = [url]
    return event


def _software_payload(record: dict[str, Any], terminal: str) -> dict[str, str]:
    issue = str(record.get("issue_statement") or "").strip()
    patch = _patch_from_messages(record)
    outcome = {
        "successful": "pass",
        "failed": "fail",
        "interrupted": "interrupted",
        "inconclusive": "unverified",
    }.get(terminal, terminal)
    payload: dict[str, str] = {"validation_outcome": outcome}
    if issue:
        payload["issue_statement"] = issue
    if patch:
        payload["implementation_patch"] = patch
    return payload


def _patch_from_messages(record: dict[str, Any]) -> str:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "tool" and message.get("name") == "apply_patch":
            return str(message.get("content") or "")
    return ""
