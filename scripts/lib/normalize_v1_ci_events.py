"""v1 review, check, timeline, and terminal events."""

from __future__ import annotations

from typing import Any

from .normalize_v1_append import (
    _actor,
    _append_event,
    _check_disposition,
    _code_state,
    _event_id,
    _head_state,
)
from .normalize_v1_common import EventContext, EventDraft


def _review_disposition(state: str) -> str:
    upper = state.upper()
    if upper == "APPROVED":
        return "successful"
    if upper in {"CHANGES_REQUESTED", "DISMISSED"}:
        return "failed"
    return "neutral"


def _add_review_events(ctx: EventContext) -> None:
    for review in ctx.raw.get("reviews") or []:
        evidence = [review.get("html_url")] if review.get("html_url") else None
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("review", ctx.source_id, review.get("id")),
                timestamp=review.get("submitted_at"),
                actor=_actor(review.get("user_login"), review.get("user_type")),
                event_type="review",
                code_state=_head_state(ctx, review.get("commit_id")),
                content=review.get("body") or "",
                disposition=_review_disposition(str(review.get("state") or "")),
                evidence=evidence,
            ),
        )


def _add_check_run_events(ctx: EventContext) -> None:
    checks = ctx.raw.get("checks") or {}
    for run in checks.get("check_runs") or []:
        ts = run.get("completed_at") or run.get("started_at") or ctx.pull.get("merged_at")
        evidence = [run.get("html_url")] if run.get("html_url") else None
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("check_run", ctx.source_id, run.get("id") or run.get("name")),
                timestamp=ts,
                actor=_actor(run.get("app_slug") or "github-actions", "Bot"),
                event_type="check_run",
                code_state=_head_state(ctx, run.get("head_sha")),
                content=f"{run.get('name')} {run.get('status')} {run.get('conclusion')}",
                disposition=_check_disposition(run.get("conclusion"), run.get("status")),
                evidence=evidence,
            ),
        )


def _add_check_suite_events(ctx: EventContext) -> None:
    checks = ctx.raw.get("checks") or {}
    for suite in checks.get("check_suites") or []:
        ts = suite.get("updated_at") or suite.get("created_at") or ctx.pull.get("merged_at")
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("check_suite", ctx.source_id, suite.get("id")),
                timestamp=ts,
                actor=_actor(suite.get("app_slug") or "github-actions", "Bot"),
                event_type="check_suite",
                code_state=_head_state(ctx, suite.get("head_sha")),
                content=f"{suite.get('app_slug')} {suite.get('status')} {suite.get('conclusion')}",
                disposition=_check_disposition(suite.get("conclusion"), suite.get("status")),
            ),
        )


def _add_commit_status_events(ctx: EventContext) -> None:
    checks = ctx.raw.get("checks") or {}
    for status in checks.get("commit_statuses") or []:
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("commit_status", ctx.source_id, status.get("id") or status.get("context")),
                timestamp=status.get("updated_at") or status.get("created_at"),
                actor=_actor("github-status", "application"),
                event_type="commit_status",
                code_state=_head_state(ctx, status.get("sha")),
                content=f"{status.get('context')}={status.get('state')}",
                disposition=_check_disposition(status.get("state"), None),
            ),
        )


def _add_check_events(ctx: EventContext) -> None:
    _add_check_run_events(ctx)
    _add_check_suite_events(ctx)
    _add_commit_status_events(ctx)


def _add_timeline_events(ctx: EventContext) -> None:
    for event in ctx.raw.get("timeline") or []:
        ev = str(event.get("event") or "timeline")
        disposition = None
        if ev in {"merged", "closed"}:
            disposition = "successful"
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("timeline", ctx.source_id, event.get("id"), ev),
                timestamp=event.get("created_at"),
                actor=_actor(event.get("actor_login"), event.get("actor_type")),
                event_type=f"timeline_{ev}",
                code_state=_head_state(ctx, event.get("commit_id")),
                content=event.get("body") or ev,
                disposition=disposition,
            ),
        )


def _add_merged_event(ctx: EventContext, pull: dict[str, Any], reverted: bool) -> None:
    disposition = "successful"
    if reverted:
        disposition = "reverted"
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("merged", ctx.source_id, pull.get("merged_at")),
            timestamp=pull.get("merged_at"),
            actor=ctx.author,
            event_type="merged",
            code_state=_code_state(
                {
                    "commit_oid": pull.get("merge_commit_sha") or ctx.head_oid,
                    "base_oid": ctx.base_oid,
                    "head_oid": ctx.head_oid,
                }
            ),
            disposition=disposition,
        ),
    )


def _add_closed_event(ctx: EventContext, pull: dict[str, Any]) -> None:
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("closed", ctx.source_id, pull.get("closed_at")),
            timestamp=pull.get("closed_at"),
            actor=ctx.author,
            event_type="closed",
            code_state=_code_state({"base_oid": ctx.base_oid, "head_oid": ctx.head_oid}),
            disposition="failed",
        ),
    )


def _add_terminal_events(ctx: EventContext) -> None:
    merge = ctx.raw.get("merge_state") or {}
    pull = ctx.pull
    if merge.get("merged") and pull.get("merged_at"):
        _add_merged_event(ctx, pull, bool(merge.get("reverted")))
        return
    if pull.get("closed_at") and not merge.get("merged"):
        _add_closed_event(ctx, pull)
