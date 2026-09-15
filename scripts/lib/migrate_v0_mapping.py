"""Field mapping helpers for lossless v0-to-v1 trajectory migration."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from validate_jsonl import SCHEMA_V1_PATH, load_schema

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised at CLI startup
    jsonschema = None

MIGRATION_TOOL_VERSION = "migrate-v0-to-v1/0.1.0"
V1_SCHEMA_VERSIONS = frozenset({"1", "1.0", "v1"})
SOURCE_SCHEMA = "pr_trajectory_v0"
COLLECTION_POLICY = "migrated-from-pr_trajectory_v0"
PROVIDER_ID = "github"
MIGRATION_ACTOR_ID = "operation-prometheus.migrate_v0_to_v1"
IMPORT_EVENT_TYPE = "v0_envelope_import"

OUTCOME_TO_TERMINAL = {
    "merged": "successful",
    "closed": "failed",
    "superseded": "reverted",
    "abandoned": "interrupted",
    "open": "inconclusive",
}
TIMESTAMP_KEYS = ("timestamp", "merged_at", "closed_at", "created_at", "updated_at")
OID_FIELD_MAP = (
    ("commit_oid", "commit_oid"),
    ("merge_commit_sha", "commit_oid"),
    ("head_oid", "head_oid"),
    ("head_sha", "head_oid"),
    ("base_oid", "base_oid"),
    ("base_sha", "base_oid"),
    ("tree_oid", "tree_oid"),
    ("before_blob", "before_blob"),
    ("after_blob", "after_blob"),
)
KNOWN_EVENT_TYPES = frozenset(
    {
        IMPORT_EVENT_TYPE,
        "commit",
        "experiment",
        "misc",
        "review",
        "validation",
        "ci",
        "test",
        "manual",
        "other",
        "patch",
        "issue",
        "pr_outcome",
    }
)
KNOWN_VALIDATION_TYPES = frozenset({"ci", "test", "manual", "review", "other"})
GIT_OID_RE = re.compile(r"^[0-9a-fA-F]{3,64}$")
REPO_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$"
)


def canonical_dumps(obj: object) -> str:
    """Stable JSON for byte-identical reruns."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def source_digest(line_bytes: bytes) -> tuple[str, int, str]:
    """Return (sha256 hex, byte size, utf-8 text) for a JSONL record line."""
    payload = line_bytes.rstrip(b"\r\n")
    return hashlib.sha256(payload).hexdigest(), len(payload), payload.decode("utf-8")


def _v1_validator() -> Any:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: pip install jsonschema")
    schema = load_schema(SCHEMA_V1_PATH)
    return jsonschema.Draft7Validator(
        schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )


def _nonempty_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _parse_utc_timestamp(value: str) -> str | None:
    try:
        iso_ts = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        dt = datetime.fromisoformat(iso_ts)
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_unavailable(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    review = record.get("review_signals")
    if not isinstance(review, list) or not review:
        missing.append("review_signals")
    if not any(key in record for key in TIMESTAMP_KEYS):
        missing.append("timestamp")
    if not _extract_code_state(record)[0]:
        missing.append("commit_oid")
    if "license" not in record or not _nonempty_str(record.get("license")):
        missing.append("license")
    return missing


def _extract_timestamp(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (timestamp, error_code). error_code is set on malformed values."""
    for key in TIMESTAMP_KEYS:
        if key not in record:
            continue
        value = record[key]
        if not isinstance(value, str) or not value.strip():
            return None, "malformed_timestamp"
        parsed = _parse_utc_timestamp(value.strip())
        if parsed is None:
            return None, "malformed_timestamp"
        return parsed, None
    return None, "unavailable_timestamp"


def _extract_code_state(record: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    """Return (code_state, error_code). error_code is set on malformed OIDs."""
    sources: list[dict[str, Any]] = [record]
    nested = record.get("repository")
    if isinstance(nested, dict):
        sources.append(nested)
    code_state: dict[str, str] = {}
    for source in sources:
        for src_key, dest_key in OID_FIELD_MAP:
            if src_key not in source:
                continue
            value = source[src_key]
            if not isinstance(value, str) or not GIT_OID_RE.fullmatch(value):
                return {}, "malformed_commit_oid"
            code_state.setdefault(dest_key, value)
    return code_state, None


def _unknown_event_reason(record: dict[str, Any]) -> str | None:
    events = record.get("events")
    if events is not None:
        if not isinstance(events, list):
            return "unknown_event"
        for event in events:
            if not isinstance(event, dict):
                return "unknown_event"
            event_type = event.get("event_type")
            if not isinstance(event_type, str) or event_type not in KNOWN_EVENT_TYPES:
                return "unknown_event"
    validation = record.get("validation")
    if isinstance(validation, list):
        for item in validation:
            if not isinstance(item, dict):
                return "unknown_event"
            vtype = item.get("type")
            if vtype is not None and vtype not in KNOWN_VALIDATION_TYPES:
                return "unknown_event"
    elif validation is not None:
        return "unknown_event"
    return None


def _split_repo(repo: object) -> tuple[str, str] | None:
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        return None
    owner, name = repo.split("/", 1)
    return owner, name


def _inline_artifact(
    *,
    artifact_id: str,
    content: str,
    raw: bytes,
    media_type: str,
    role: str,
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "media_type": media_type,
        "byte_size": len(raw),
        "availability": "inline",
        "reproduction_role": role,
        "content": content,
    }


def _candidate_envelope(
    record: dict[str, Any],
    *,
    source_text: str,
    source_bytes: bytes,
    digest: str,
    timestamp: str,
    code_state: dict[str, str],
    unavailable: list[str],
) -> dict[str, Any] | str:
    traj_id = _nonempty_str(record.get("id"))
    if traj_id is None:
        return "missing_id"
    repo_parts = _split_repo(record.get("repo"))
    if repo_parts is None:
        return "malformed_repo"
    owner, name = repo_parts
    outcome = record.get("outcome")
    if not isinstance(outcome, str) or outcome not in OUTCOME_TO_TERMINAL:
        return "unknown_outcome"
    terminal = OUTCOME_TO_TERMINAL[outcome]
    urls = record.get("source_urls")
    evidence: list[str] = []
    if isinstance(urls, list):
        evidence = [u for u in urls if isinstance(u, str) and u]
    if not evidence and not code_state:
        return "unanchored_event"

    payload: dict[str, str] = {}
    issue = _nonempty_str(record.get("issue_context"))
    if issue is not None:
        payload["issue_statement"] = issue
    before = _nonempty_str(record.get("before_context"))
    if before is not None:
        payload["pre_change_state"] = before
    patch = _nonempty_str(record.get("patch"))
    if patch is not None:
        payload["implementation_patch"] = patch
    validation = record.get("validation")
    if isinstance(validation, list) and validation:
        payload["validation_outcome"] = canonical_dumps(validation)
    if not payload:
        return "unavailable_software_payload"

    event: dict[str, Any] = {
        "actor": {
            "disclosed_identity": MIGRATION_TOOL_VERSION,
            "id": MIGRATION_ACTOR_ID,
            "type": "application",
        },
        "content": traj_id,
        "disposition": terminal,
        "event_id": f"{digest[:16]}:v0-import",
        "event_type": IMPORT_EVENT_TYPE,
        "timestamp": timestamp,
    }
    if evidence:
        event["evidence_references"] = list(evidence)
    if code_state:
        event["code_state"] = dict(code_state)

    artifacts = [
        _inline_artifact(
            artifact_id=f"{digest[:16]}:source-v0",
            content=source_text,
            raw=source_bytes,
            media_type="application/json",
            role="source_record",
        )
    ]
    if patch is not None:
        patch_bytes = patch.encode("utf-8")
        artifacts.append(
            _inline_artifact(
                artifact_id=f"{digest[:16]}:patch",
                content=patch,
                raw=patch_bytes,
                media_type="text/x-diff",
                role="patch",
            )
        )

    license_value = _nonempty_str(record.get("license")) or "NOASSERTION"
    envelope: dict[str, Any] = {
        "artifacts": artifacts,
        "collection_policy": COLLECTION_POLICY,
        "collector_version": MIGRATION_TOOL_VERSION,
        "events": [event],
        "license": license_value,
        "migration": {
            "source_byte_size": len(source_bytes),
            "source_schema": SOURCE_SCHEMA,
            "source_sha256": digest,
            "tool_version": MIGRATION_TOOL_VERSION,
            "unavailable_fields": list(unavailable),
        },
        "provenance": (
            f"migrated-from-{SOURCE_SCHEMA}@{MIGRATION_TOOL_VERSION};source_sha256={digest}"
        ),
        "provider_id": PROVIDER_ID,
        "repository": {
            "name": name,
            "owner": owner,
            "url": f"https://github.com/{owner}/{name}",
        },
        "schema_version": "1.0",
        "software_payload": payload,
        "source_id": traj_id,
        "terminal_disposition": terminal,
        "trajectory_id": traj_id,
        "trajectory_type": "software",
        "v0_fields": record,
    }
    quality = record.get("quality_score")
    if isinstance(quality, bool) or not isinstance(quality, (int, float)):
        pass
    elif math.isfinite(float(quality)):
        envelope["evidence_quality"] = {"signal_to_noise": float(quality)}
    return envelope
