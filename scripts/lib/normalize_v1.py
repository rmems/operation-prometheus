"""Normalize raw PR records into typed trajectory v1 objects."""

from __future__ import annotations

from typing import Any

from . import __version__
from .github_client import parse_repo
from .normalize import resolve_source_license
from .normalize_v1_common import (
    COLLECTION_POLICY,
    V1_SCHEMA_VERSION,
    V1NormalizeOptions,
    _terminal_disposition,
)
from .normalize_v1_events import _ensure_min_event, _event_context, build_v1_events
from .normalize_v1_payload import (
    _assemble_artifacts,
    _evidence_quality,
    _lineage,
    _patch_artifact,
    _task_family,
    _typed_payloads,
)

__all__ = [
    "COLLECTION_POLICY",
    "V1_SCHEMA_VERSION",
    "V1NormalizeOptions",
    "build_v1_events",
    "normalize_record_v1",
]


def normalize_record_v1(
    raw: dict[str, Any],
    card: dict[str, Any] | None = None,
    options: V1NormalizeOptions | None = None,
) -> dict[str, Any]:
    """Build a schema-v1 trajectory from a raw PR record."""
    card = card or {}
    opts = options or V1NormalizeOptions()
    source = raw.get("source") or {}
    repo = str(source.get("repo") or card.get("source_repo") or "unknown/unknown")
    pr = int(source.get("pr_number") or 0)
    owner, name = parse_repo(repo)
    traj_id = f"{owner}-{name}-{pr}"
    source_id = source.get("html_url") or f"https://github.com/{owner}/{name}/pull/{pr}"
    pull = raw.get("pull") or {}
    license_id = opts.source_license or resolve_source_license(source, card)

    patch_text, patch_art = _patch_artifact(raw, opts.max_patch_bytes, opts.raw_path)
    events = build_v1_events(raw, source_id)
    if not events:
        ctx = _event_context(raw, source_id)
        ctx.events = events
        _ensure_min_event(ctx)

    task_family = _task_family(card)
    record: dict[str, Any] = {
        "schema_version": V1_SCHEMA_VERSION,
        "trajectory_id": traj_id,
        "trajectory_type": task_family,
        "provider_id": "github",
        "source_id": source_id,
        "collector_version": str(raw.get("collector_version") or __version__),
        "repository": {
            "owner": owner,
            "name": name,
            "url": f"https://github.com/{owner}/{name}",
            "commit_oid": pull.get("merge_commit_sha") or pull.get("head_sha"),
            "base_oid": pull.get("base_sha"),
            "head_oid": pull.get("head_sha"),
        },
        "license": license_id,
        "provenance": source_id,
        "collection_policy": COLLECTION_POLICY,
        "takedown_state": "active",
        "terminal_disposition": _terminal_disposition(raw),
        "evidence_quality": _evidence_quality(raw, events),
        "events": events,
        "artifacts": _assemble_artifacts(raw, patch_art, opts.artifact_store),
        "lineage": _lineage(raw, source_id),
    }
    record.update(_typed_payloads(raw, patch_text, task_family))
    return record
