"""Helpers for constructing v1 trajectory events."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .bots import is_bot_user
from .normalize import outcome_for
from .normalize_v1_common import EventContext, EventDraft


def _utc(ts: str | None) -> str | None:
    if not isinstance(ts, str):
        return None
    raw = ts.strip()
    if not raw:
        return None
    return _parse_utc(raw)


def _as_iso(raw: str) -> str:
    if raw.endswith(("Z", "z")):
        return raw[:-1] + "+00:00"
    return raw


def _parse_utc(raw: str) -> str | None:
    try:
        dt = datetime.fromisoformat(_as_iso(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError, OverflowError):
        return None


def _actor_kind(login: str, user_type: str | None) -> str:
    lowered = (user_type or "").lower()
    if lowered == "bot":
        return "bot"
    if is_bot_user(login, user_type):
        return "bot"
    if lowered in {"application", "app"}:
        return "application"
    return "human"


def _actor(login: str | None, user_type: str | None) -> dict[str, str]:
    login = (login or "unknown").strip() or "unknown"
    return {"type": _actor_kind(login, user_type), "id": login}


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
    return _outcome_disposition(outcome_for(raw))


def _outcome_disposition(outcome: str) -> str:
    if outcome == "merged":
        return "successful"
    if outcome == "closed":
        return "failed"
    if outcome == "open":
        return "interrupted"
    return "inconclusive"


def _copy_optional(event: dict[str, Any], key: str, value: Any) -> None:
    if value:
        event[key] = value


def _append_event(events: list[dict[str, Any]], draft: EventDraft) -> None:
    ts = _utc(draft.timestamp)
    if not ts:
        return
    event: dict[str, Any] = {
        "event_id": draft.event_id,
        "timestamp": ts,
        "actor": draft.actor,
        "event_type": draft.event_type,
    }
    _copy_optional(event, "code_state", draft.code_state)
    _copy_optional(event, "evidence_references", draft.evidence)
    _copy_optional(event, "disposition", draft.disposition)
    _copy_optional(event, "content", draft.content)
    events.append(event)
