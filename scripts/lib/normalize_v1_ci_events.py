"""v1 timeline and terminal events."""

from __future__ import annotations

from typing import Any

from .normalize_v1_append import _actor, _code_state, _head_state
from .normalize_v1_check_events import _add_check_events, _add_review_events
from .normalize_v1_common import EventContext
from .normalize_v1_event_spec import EventSpec, _append_spec

__all__ = [
    "_add_check_events",
    "_add_review_events",
    "_add_terminal_events",
    "_add_timeline_events",
]


def _add_timeline_events(ctx: EventContext) -> None:
    for event in ctx.raw.get("timeline") or []:
        _append_spec(ctx, _timeline_spec(ctx, event))


def _timeline_disposition(event_name: str) -> str | None:
    if event_name in {"merged", "closed"}:
        return "successful"
    return None


def _timeline_spec(ctx: EventContext, event: dict[str, Any]) -> EventSpec:
    ev = str(event.get("event") or "timeline")
    return EventSpec(
        kind="timeline",
        stamp_parts=(event.get("id"), ev),
        timestamp=event.get("created_at"),
        actor=_actor(event.get("actor_login"), event.get("actor_type")),
        event_type=f"timeline_{ev}",
        code_state=_head_state(ctx, event.get("commit_id")),
        content=event.get("body") or ev,
        disposition=_timeline_disposition(ev),
    )


def _merged_disposition(reverted: bool) -> str:
    if reverted:
        return "reverted"
    return "successful"


def _merged_spec(ctx: EventContext, pull: dict[str, Any], reverted: bool) -> EventSpec:
    return EventSpec(
        kind="merged",
        stamp_parts=(pull.get("merged_at"),),
        timestamp=pull.get("merged_at"),
        actor=ctx.author,
        code_state=_code_state(
            {
                "commit_oid": pull.get("merge_commit_sha") or ctx.head_oid,
                "base_oid": ctx.base_oid,
                "head_oid": ctx.head_oid,
            }
        ),
        disposition=_merged_disposition(reverted),
    )


def _closed_spec(ctx: EventContext, pull: dict[str, Any]) -> EventSpec:
    return EventSpec(
        kind="closed",
        stamp_parts=(pull.get("closed_at"),),
        timestamp=pull.get("closed_at"),
        actor=ctx.author,
        code_state=_code_state({"base_oid": ctx.base_oid, "head_oid": ctx.head_oid}),
        disposition="failed",
    )


def _is_merged(merge: dict[str, Any], pull: dict[str, Any]) -> bool:
    if not merge.get("merged"):
        return False
    return bool(pull.get("merged_at"))


def _is_closed_unmerged(merge: dict[str, Any], pull: dict[str, Any]) -> bool:
    if merge.get("merged"):
        return False
    return bool(pull.get("closed_at"))


def _add_terminal_events(ctx: EventContext) -> None:
    merge = ctx.raw.get("merge_state") or {}
    pull = ctx.pull
    if _is_merged(merge, pull):
        _append_spec(ctx, _merged_spec(ctx, pull, bool(merge.get("reverted"))))
        return
    if _is_closed_unmerged(merge, pull):
        _append_spec(ctx, _closed_spec(ctx, pull))
