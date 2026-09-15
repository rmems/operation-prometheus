"""Chronological v1 event construction from a raw PR record."""

from __future__ import annotations

from typing import Any

from .normalize_v1_common import (
    EventContext,
    EventDraft,
    _actor,
    _check_disposition,
    _code_state,
    _event_id,
    _head_state,
    _utc,
)

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
    if draft.code_state:
        event["code_state"] = draft.code_state
    if draft.evidence:
        event["evidence_references"] = draft.evidence
    if draft.disposition:
        event["disposition"] = draft.disposition
    if draft.content:
        event["content"] = draft.content
    events.append(event)


def _event_context(raw: dict[str, Any], source_id: str) -> EventContext:
    pull = raw.get("pull") or {}
    return EventContext(
        raw=raw,
        source_id=source_id,
        pull=pull,
        base_oid=pull.get("base_sha"),
        head_oid=pull.get("head_sha"),
        author=_actor(pull.get("user_login"), pull.get("user_type")),
        events=[],
    )


def _add_pr_opened(ctx: EventContext) -> None:
    pull = ctx.pull
    created = pull.get("created_at")
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("pr_opened", ctx.source_id, created or pull.get("title")),
            timestamp=created or pull.get("updated_at") or pull.get("merged_at"),
            actor=ctx.author,
            event_type="issue_opened" if not created else "pr_opened",
            code_state=_code_state({"base_oid": ctx.base_oid, "head_oid": ctx.head_oid}),
            content=pull.get("title") or "",
        ),
    )


def _add_linked_issue(ctx: EventContext, issue: dict[str, Any]) -> None:
    evidence = [issue.get("html_url")] if issue.get("html_url") else None
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("linked_issue", ctx.source_id, issue.get("number")),
            timestamp=issue.get("created_at") or ctx.pull.get("created_at"),
            actor=_actor(issue.get("user_login"), issue.get("user_type")),
            event_type="issue_opened",
            content=issue.get("title") or "",
            evidence=evidence,
        ),
    )
    for comment in issue.get("comments") or []:
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("issue_comment", ctx.source_id, comment.get("id")),
                timestamp=comment.get("created_at"),
                actor=_actor(comment.get("user_login"), comment.get("user_type")),
                event_type="issue_comment",
                content=comment.get("body") or "",
            ),
        )


def _add_opened_events(ctx: EventContext) -> None:
    _add_pr_opened(ctx)
    for issue in ctx.raw.get("linked_issues") or []:
        _add_linked_issue(ctx, issue)


def _add_commit_events(ctx: EventContext) -> None:
    for commit in ctx.raw.get("commits") or []:
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("commit", ctx.source_id, commit.get("sha")),
                timestamp=commit.get("date"),
                actor=_actor(commit.get("author_login"), commit.get("author_type")),
                event_type="commit",
                code_state=_code_state(
                    {
                        "commit_oid": commit.get("sha"),
                        "base_oid": ctx.base_oid,
                        "head_oid": commit.get("sha") or ctx.head_oid,
                        "tree_oid": commit.get("tree_oid"),
                    }
                ),
                content=commit.get("message") or "",
                disposition="successful",
            ),
        )


def _add_pr_comment_events(ctx: EventContext) -> None:
    default_state = _code_state({"base_oid": ctx.base_oid, "head_oid": ctx.head_oid})
    for comment in ctx.raw.get("issue_comments") or []:
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("pr_comment", ctx.source_id, comment.get("id")),
                timestamp=comment.get("created_at"),
                actor=_actor(comment.get("user_login"), comment.get("user_type")),
                event_type="issue_comment",
                code_state=default_state,
                content=comment.get("body") or "",
            ),
        )


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


def _review_comment_body(comment: dict[str, Any]) -> tuple[str, list[str] | None]:
    refs: list[str] = []
    if comment.get("html_url"):
        refs.append(comment["html_url"])
    if comment.get("in_reply_to_id"):
        refs.append(f"in_reply_to:{comment['in_reply_to_id']}")
    hunk = comment.get("diff_hunk") or ""
    body = comment.get("body") or ""
    content = f"{hunk}\n\n{body}".strip() if hunk else body
    loc = f"{comment.get('path')}:{comment.get('line') or comment.get('original_line')}"
    return f"{loc}\n{content}".strip(), refs or None


def _add_review_comment_events(ctx: EventContext) -> None:
    for comment in ctx.raw.get("review_comments") or []:
        content, refs = _review_comment_body(comment)
        oid = comment.get("commit_id") or comment.get("original_commit_id")
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("review_comment", ctx.source_id, comment.get("id")),
                timestamp=comment.get("created_at"),
                actor=_actor(comment.get("user_login"), comment.get("user_type")),
                event_type="review_comment",
                code_state=_code_state(
                    {
                        "commit_oid": oid or ctx.head_oid,
                        "base_oid": ctx.base_oid,
                        "head_oid": comment.get("commit_id") or ctx.head_oid,
                    }
                ),
                content=content,
                evidence=refs,
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
        _append_event(
            ctx.events,
            EventDraft(
                event_id=_event_id("timeline", ctx.source_id, event.get("id"), ev),
                timestamp=event.get("created_at"),
                actor=_actor(event.get("actor_login"), event.get("actor_type")),
                event_type=f"timeline_{ev}",
                code_state=_head_state(ctx, event.get("commit_id")),
                content=event.get("body") or ev,
                disposition="successful" if ev in {"merged", "closed"} else None,
            ),
        )


def _add_terminal_events(ctx: EventContext) -> None:
    merge = ctx.raw.get("merge_state") or {}
    pull = ctx.pull
    if merge.get("merged") and pull.get("merged_at"):
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
                disposition="reverted" if merge.get("reverted") else "successful",
            ),
        )
        return
    if pull.get("closed_at") and not merge.get("merged"):
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


def _sort_unique_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events.sort(
        key=lambda e: (
            e["timestamp"],
            99 if e["event_type"] in {"merged", "closed"} else 50,
            e["event_id"],
        )
    )
    uniq: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if event["event_id"] in seen:
            continue
        seen.add(event["event_id"])
        uniq.append(event)
    return uniq


def build_v1_events(raw: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    """Build chronological v1 events from a raw PR record."""
    ctx = _event_context(raw, source_id)
    _add_opened_events(ctx)
    _add_commit_events(ctx)
    _add_pr_comment_events(ctx)
    _add_review_events(ctx)
    _add_review_comment_events(ctx)
    _add_check_events(ctx)
    _add_timeline_events(ctx)
    _add_terminal_events(ctx)
    return _sort_unique_events(ctx.events)


def _ensure_min_event(ctx: EventContext) -> None:
    if ctx.events:
        return
    pull = ctx.pull
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("pr_opened", ctx.source_id, (ctx.raw.get("source") or {}).get("pr_number")),
            timestamp="1970-01-01T00:00:00Z",
            actor=_actor(pull.get("user_login"), pull.get("user_type")),
            event_type="pr_opened",
            code_state=_code_state({"base_oid": pull.get("base_sha"), "head_oid": pull.get("head_sha")}),
            content=pull.get("title") or "undated pull request",
            disposition="inconclusive",
        ),
    )

