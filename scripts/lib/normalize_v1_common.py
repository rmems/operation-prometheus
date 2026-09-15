"""Shared types and helpers for trajectory v1 normalization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bots import is_bot_user
from .cas import ContentAddressedStore
from .normalize import outcome_for

V1_SCHEMA_VERSION = "1.0"
COLLECTION_POLICY = "public-github-read-only"



@dataclass
class V1NormalizeOptions:
    artifact_store: ContentAddressedStore | None = None
    max_patch_bytes: int = 96 * 1024
    source_license: str | None = None
    raw_path: Path | None = None


@dataclass
class EventDraft:
    event_id: str
    timestamp: str | None
    actor: dict[str, str]
    event_type: str
    code_state: dict[str, str] | None = None
    evidence: list[str] | None = None
    disposition: str | None = None
    content: str | None = None


@dataclass
class EventContext:
    raw: dict[str, Any]
    source_id: str
    pull: dict[str, Any]
    base_oid: Any
    head_oid: Any
    author: dict[str, str]
    events: list[dict[str, Any]]


def _utc(ts: str | None) -> str | None:
    if not isinstance(ts, str) or not ts.strip():
        return None
    raw = ts.strip()
    try:
        iso = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError, OverflowError):
        return None


def _actor(login: str | None, user_type: str | None) -> dict[str, str]:
    login = (login or "unknown").strip() or "unknown"
    kind = "human"
    if user_type and user_type.lower() == "bot":
        kind = "bot"
    elif is_bot_user(login, user_type):
        kind = "bot"
    elif user_type and user_type.lower() in {"application", "app"}:
        kind = "application"
    return {"type": kind, "id": login}


def _event_id(kind: str, source: str, *parts: Any) -> str:
    blob = "|".join(str(p) for p in (kind, source, *parts))
    return kind + ":" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _code_state(values: dict[str, Any] | None = None) -> dict[str, str]:
    state: dict[str, str] = {}
    if not values:
        return state
    for key in ("commit_oid", "base_oid", "head_oid", "tree_oid", "before_blob", "after_blob"):
        val = values.get(key)
        if val:
            state[key] = str(val)
    return state


def _head_state(ctx: EventContext, commit_oid: Any) -> dict[str, str]:
    return _code_state(
        {
            "commit_oid": commit_oid or ctx.head_oid,
            "base_oid": ctx.base_oid,
            "head_oid": commit_oid or ctx.head_oid,
        }
    )


def _check_disposition(conclusion: str | None, status: str | None) -> str:
    conc = (conclusion or "").lower()
    if conc in {"success"}:
        return "successful"
    if conc in {"failure", "timed_out", "startup_failure", "action_required", "cancelled"}:
        return "failed"
    if conc in {"neutral", "skipped"}:
        return "neutral"
    if (status or "").lower() in {"queued", "in_progress"}:
        return "interrupted"
    return "inconclusive"


def _terminal_disposition(raw: dict[str, Any]) -> str:
    merge = raw.get("merge_state") or {}
    if merge.get("reverted"):
        return "reverted"
    outcome = outcome_for(raw)
    if outcome == "merged":
        return "successful"
    if outcome == "closed":
        return "failed"
    if outcome == "open":
        return "interrupted"
    return "inconclusive"
