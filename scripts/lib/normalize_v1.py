"""Normalize raw PR records into typed trajectory v1 objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import __version__
from .github_client import parse_repo
from .normalize import resolve_source_license
from .normalize_v1_append import _terminal_disposition
from .normalize_v1_common import (
    COLLECTION_POLICY,
    V1_SCHEMA_VERSION,
    V1NormalizeOptions,
)
from .normalize_v1_artifacts import _assemble_artifacts, _patch_artifact
from .normalize_v1_events import _ensure_min_event, _event_context, build_v1_events
from .normalize_v1_payload import (
    _evidence_quality,
    _lineage,
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


@dataclass
class V1Identity:
    owner: str
    name: str
    source_id: str
    traj_id: str
    pull: dict[str, Any]
    license_id: str


def _v1_source(raw: dict[str, Any], card: dict[str, Any], opts: V1NormalizeOptions) -> V1Identity:
    source = raw.get("source") or {}
    repo = str(source.get("repo") or card.get("source_repo") or "unknown/unknown")
    pr = int(source.get("pr_number") or 0)
    owner, name = parse_repo(repo)
    html = source.get("html_url")
    source_id = html or f"https://github.com/{owner}/{name}/pull/{pr}"
    return V1Identity(
        owner=owner,
        name=name,
        source_id=source_id,
        traj_id=f"{owner}-{name}-{pr}",
        pull=raw.get("pull") or {},
        license_id=opts.source_license or resolve_source_license(source, card),
    )


def _events_for(raw: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    events = build_v1_events(raw, source_id)
    if events:
        return events
    ctx = _event_context(raw, source_id)
    _ensure_min_event(ctx)
    return ctx.events


def _repo_block(ident: V1Identity) -> dict[str, Any]:
    pull = ident.pull
    return {
        "owner": ident.owner,
        "name": ident.name,
        "url": f"https://github.com/{ident.owner}/{ident.name}",
        "commit_oid": pull.get("merge_commit_sha") or pull.get("head_sha"),
        "base_oid": pull.get("base_sha"),
        "head_oid": pull.get("head_sha"),
    }


def _v1_meta(ident: V1Identity, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": V1_SCHEMA_VERSION,
        "trajectory_id": ident.traj_id,
        "provider_id": "github",
        "source_id": ident.source_id,
        "collector_version": str(raw.get("collector_version") or __version__),
        "license": ident.license_id,
        "provenance": ident.source_id,
        "collection_policy": COLLECTION_POLICY,
        "takedown_state": "active",
    }


def _v1_core(
    ident: V1Identity,
    events: list[dict[str, Any]],
    raw: dict[str, Any],
    task_family: str,
) -> dict[str, Any]:
    record = _v1_meta(ident, raw)
    record["trajectory_type"] = task_family
    record["repository"] = _repo_block(ident)
    record["terminal_disposition"] = _terminal_disposition(raw)
    record["evidence_quality"] = _evidence_quality(raw, events)
    record["events"] = events
    record["lineage"] = _lineage(raw, ident.source_id)
    return record


def normalize_record_v1(
    raw: dict[str, Any],
    card: dict[str, Any] | None = None,
    options: V1NormalizeOptions | None = None,
) -> dict[str, Any]:
    """Build a schema-v1 trajectory from a raw PR record."""
    opts = options or V1NormalizeOptions()
    card = card or {}
    ident = _v1_source(raw, card, opts)
    patch_text, patch_art = _patch_artifact(raw, opts.max_patch_bytes, opts.raw_path)
    events = _events_for(raw, ident.source_id)
    task_family = _task_family(card)
    record = _v1_core(ident, events, raw, task_family)
    record["artifacts"] = _assemble_artifacts(raw, patch_art, opts.artifact_store)
    record.update(_typed_payloads(raw, patch_text, task_family))
    return record
