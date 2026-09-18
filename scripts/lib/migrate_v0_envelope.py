"""Build a candidate trajectory-v1 envelope from a validated v0 record."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from .migrate_v0_constants import (
    COLLECTION_POLICY,
    IMPORT_EVENT_TYPE,
    MIGRATION_ACTOR_ID,
    MIGRATION_TOOL_VERSION,
    OUTCOME_TO_TERMINAL,
    PROVIDER_ID,
    SOURCE_SCHEMA,
    SOURCE_URL_RE,
    UNMAPPABLE_OUTCOMES,
)
from .migrate_v0_fields import nonempty_str, split_repo
from .migrate_v0_text import canonical_dumps


@dataclass(frozen=True)
class MappingContext:
    record: dict[str, Any]
    source_text: str
    source_bytes: bytes
    digest: str
    timestamp: str
    code_state: dict[str, str]
    unavailable: list[str]


@dataclass(frozen=True)
class Identity:
    traj_id: str
    owner: str
    name: str
    terminal: str


def candidate_envelope(ctx: MappingContext) -> dict[str, Any] | str:
    identity = _identity(ctx.record)
    if isinstance(identity, str):
        return identity
    evidence = _evidence_urls(ctx.record)
    if isinstance(evidence, str):
        return evidence
    if not evidence and not ctx.code_state:
        return "unanchored_event"
    payload = _software_payload(ctx.record)
    if isinstance(payload, str):
        return payload
    return _assemble(ctx, identity, evidence, payload)


def _identity(record: dict[str, Any]) -> Identity | str:
    traj_id = nonempty_str(record.get("id"))
    if traj_id is None:
        return "missing_id"
    repo_parts = split_repo(record.get("repo"))
    if repo_parts is None:
        return "malformed_repo"
    outcome = record.get("outcome")
    if outcome in UNMAPPABLE_OUTCOMES:
        return "unmappable_outcome"
    if not isinstance(outcome, str) or outcome not in OUTCOME_TO_TERMINAL:
        return "unknown_outcome"
    owner, name = repo_parts
    return Identity(traj_id, owner, name, OUTCOME_TO_TERMINAL[outcome])


def _evidence_urls(record: dict[str, Any]) -> list[str] | str:
    urls = record.get("source_urls")
    if urls is None:
        return []
    if not isinstance(urls, list):
        return "malformed_source_url"
    evidence: list[str] = []
    for url in urls:
        if not isinstance(url, str) or not url:
            return "malformed_source_url"
        if not SOURCE_URL_RE.fullmatch(url):
            return "malformed_source_url"
        evidence.append(url)
    return evidence


def _software_payload(record: dict[str, Any]) -> dict[str, str] | str:
    payload: dict[str, str] = {}
    _put_text(payload, "issue_statement", record.get("issue_context"))
    _put_text(payload, "pre_change_state", record.get("before_context"))
    _put_text(payload, "implementation_patch", record.get("patch"))
    validation = record.get("validation")
    if isinstance(validation, list) and validation:
        payload["validation_outcome"] = canonical_dumps(validation)
    if payload:
        return payload
    return "unavailable_software_payload"


def _put_text(payload: dict[str, str], key: str, value: object) -> None:
    text = nonempty_str(value)
    if text is not None:
        payload[key] = text


def _assemble(
    ctx: MappingContext,
    identity: Identity,
    evidence: list[str],
    payload: dict[str, str],
) -> dict[str, Any]:
    event = _import_event(ctx, identity, evidence)
    artifacts = _artifacts(ctx, payload.get("implementation_patch"))
    envelope = _base_envelope(ctx, identity, _EnvelopeBody(payload, event, artifacts))
    _maybe_quality(envelope, ctx.record.get("quality_score"))
    return envelope


@dataclass(frozen=True)
class _EnvelopeBody:
    payload: dict[str, str]
    event: dict[str, Any]
    artifacts: list[dict[str, Any]]


def _import_event(
    ctx: MappingContext, identity: Identity, evidence: list[str]
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "actor": {
            "disclosed_identity": MIGRATION_TOOL_VERSION,
            "id": MIGRATION_ACTOR_ID,
            "type": "application",
        },
        "content": identity.traj_id,
        "disposition": identity.terminal,
        "event_id": f"{ctx.digest[:16]}:v0-import",
        "event_type": IMPORT_EVENT_TYPE,
        "timestamp": ctx.timestamp,
    }
    if evidence:
        event["evidence_references"] = list(evidence)
    if ctx.code_state:
        event["code_state"] = dict(ctx.code_state)
    return event


def _artifacts(ctx: MappingContext, patch: str | None) -> list[dict[str, Any]]:
    artifacts = [_inline_artifact(ctx.digest, ctx.source_text, ctx.source_bytes)]
    if patch is None:
        return artifacts
    patch_bytes = patch.encode("utf-8")
    artifacts.append(
        {
            "id": f"{ctx.digest[:16]}:patch",
            "sha256": hashlib.sha256(patch_bytes).hexdigest(),
            "media_type": "text/x-diff",
            "byte_size": len(patch_bytes),
            "availability": "inline",
            "reproduction_role": "patch",
            "content": patch,
        }
    )
    return artifacts


def _inline_artifact(digest: str, content: str, raw: bytes) -> dict[str, Any]:
    return {
        "id": f"{digest[:16]}:source-v0",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "media_type": "application/json",
        "byte_size": len(raw),
        "availability": "inline",
        "reproduction_role": "source_record",
        "content": content,
    }


def _base_envelope(
    ctx: MappingContext,
    identity: Identity,
    body: _EnvelopeBody,
) -> dict[str, Any]:
    license_value = nonempty_str(ctx.record.get("license")) or "NOASSERTION"
    return {
        "artifacts": body.artifacts,
        "collection_policy": COLLECTION_POLICY,
        "collector_version": MIGRATION_TOOL_VERSION,
        "events": [body.event],
        "license": license_value,
        "migration": {
            "source_byte_size": len(ctx.source_bytes),
            "source_schema": SOURCE_SCHEMA,
            "source_sha256": ctx.digest,
            "tool_version": MIGRATION_TOOL_VERSION,
            "unavailable_fields": list(ctx.unavailable),
        },
        "provenance": (
            f"migrated-from-{SOURCE_SCHEMA}@{MIGRATION_TOOL_VERSION};source_sha256={ctx.digest}"
        ),
        "provider_id": PROVIDER_ID,
        "repository": {
            "name": identity.name,
            "owner": identity.owner,
            "url": f"https://github.com/{identity.owner}/{identity.name}",
        },
        "schema_version": "1.0",
        "software_payload": body.payload,
        "source_id": identity.traj_id,
        "terminal_disposition": identity.terminal,
        "trajectory_id": identity.traj_id,
        "trajectory_type": "software",
        "v0_fields": ctx.record,
    }


def _maybe_quality(envelope: dict[str, Any], quality: object) -> None:
    if isinstance(quality, bool):
        return
    if isinstance(quality, int):
        envelope["evidence_quality"] = {"signal_to_noise": quality}
        return
    if isinstance(quality, float) and math.isfinite(quality):
        envelope["evidence_quality"] = {"signal_to_noise": quality}
