"""v1 review and CI check events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalize_v1_append import _actor, _check_disposition, _head_state
from .normalize_v1_common import EventContext
from .normalize_v1_event_spec import EventSpec, _append_spec, _url_evidence


def _review_disposition(state: str) -> str:
    upper = state.upper()
    if upper == "APPROVED":
        return "successful"
    if upper in {"CHANGES_REQUESTED", "DISMISSED"}:
        return "failed"
    return "neutral"


def _checks_block(ctx: EventContext) -> dict[str, Any]:
    checks = ctx.raw.get("checks") or {}
    if isinstance(checks, dict):
        return checks
    return {}


def _add_review_events(ctx: EventContext) -> None:
    for review in ctx.raw.get("reviews") or []:
        _append_spec(ctx, _review_spec(ctx, review))


def _review_spec(ctx: EventContext, review: dict[str, Any]) -> EventSpec:
    return EventSpec(
        kind="review",
        stamp_parts=(review.get("id"),),
        timestamp=review.get("submitted_at"),
        actor=_actor(review.get("user_login"), review.get("user_type")),
        code_state=_head_state(ctx, review.get("commit_id")),
        content=review.get("body") or "",
        disposition=_review_disposition(str(review.get("state") or "")),
        evidence=_url_evidence(review.get("html_url")),
    )


@dataclass(frozen=True)
class AppCheck:
    kind: str
    item_id: Any
    timestamp: Any
    content: str
    evidence_url: Any = None


def _app_check_spec(ctx: EventContext, item: dict[str, Any], check: AppCheck) -> EventSpec:
    return EventSpec(
        kind=check.kind,
        stamp_parts=(check.item_id,),
        timestamp=check.timestamp,
        actor=_actor(item.get("app_slug") or "github-actions", "Bot"),
        code_state=_head_state(ctx, item.get("head_sha")),
        content=check.content,
        disposition=_check_disposition(item.get("conclusion"), item.get("status")),
        evidence=_url_evidence(check.evidence_url),
    )


def _add_check_run_events(ctx: EventContext) -> None:
    for run in _checks_block(ctx).get("check_runs") or []:
        _append_spec(ctx, _check_run_spec(ctx, run))


def _check_run_spec(ctx: EventContext, run: dict[str, Any]) -> EventSpec:
    ts = run.get("completed_at") or run.get("started_at") or ctx.pull.get("merged_at")
    check = AppCheck(
        kind="check_run",
        item_id=run.get("id") or run.get("name"),
        timestamp=ts,
        content=f"{run.get('name')} {run.get('status')} {run.get('conclusion')}",
        evidence_url=run.get("html_url"),
    )
    return _app_check_spec(ctx, run, check)


def _add_check_suite_events(ctx: EventContext) -> None:
    for suite in _checks_block(ctx).get("check_suites") or []:
        _append_spec(ctx, _check_suite_spec(ctx, suite))


def _check_suite_spec(ctx: EventContext, suite: dict[str, Any]) -> EventSpec:
    ts = suite.get("updated_at") or suite.get("created_at") or ctx.pull.get("merged_at")
    check = AppCheck(
        kind="check_suite",
        item_id=suite.get("id"),
        timestamp=ts,
        content=f"{suite.get('app_slug')} {suite.get('status')} {suite.get('conclusion')}",
    )
    return _app_check_spec(ctx, suite, check)


def _add_commit_status_events(ctx: EventContext) -> None:
    for status in _checks_block(ctx).get("commit_statuses") or []:
        _append_spec(ctx, _commit_status_spec(ctx, status))


def _commit_status_spec(ctx: EventContext, status: dict[str, Any]) -> EventSpec:
    return EventSpec(
        kind="commit_status",
        stamp_parts=(status.get("id") or status.get("context"),),
        timestamp=status.get("updated_at") or status.get("created_at"),
        actor=_actor("github-status", "application"),
        code_state=_head_state(ctx, status.get("sha")),
        content=f"{status.get('context')}={status.get('state')}",
        disposition=_check_disposition(status.get("state"), None),
    )


def _add_check_events(ctx: EventContext) -> None:
    _add_check_run_events(ctx)
    _add_check_suite_events(ctx)
    _add_commit_status_events(ctx)
