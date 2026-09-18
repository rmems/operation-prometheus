"""Chronological v1 event construction from a raw PR record."""

from __future__ import annotations

from typing import Any

from .normalize_v1_append import (
    _actor,
    _append_event,
    _code_state,
    _event_id,
)
from .normalize_v1_ci_events import (
    _add_check_events,
    _add_review_events,
    _add_terminal_events,
    _add_timeline_events,
)
from .normalize_v1_common import EventContext, EventDraft


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
    event_type = "pr_opened"
    if not created:
        event_type = "issue_opened"
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id("pr_opened", ctx.source_id, created or pull.get("title")),
            timestamp=created or pull.get("updated_at") or pull.get("merged_at"),
            actor=ctx.author,
            event_type=event_type,
            code_state=_code_state({"base_oid": ctx.base_oid, "head_oid": ctx.head_oid}),
            content=pull.get("title") or "",
        ),
    )


def _add_issue_comment(ctx: EventContext, comment: dict[str, Any]) -> None:
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
        _add_issue_comment(ctx, comment)


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


def _review_comment_refs(comment: dict[str, Any]) -> list[str] | None:
    refs: list[str] = []
    if comment.get("html_url"):
        refs.append(comment["html_url"])
    if comment.get("in_reply_to_id"):
        refs.append(f"in_reply_to:{comment['in_reply_to_id']}")
    if refs:
        return refs
    return None


def _review_comment_body(comment: dict[str, Any]) -> str:
    hunk = comment.get("diff_hunk") or ""
    body = comment.get("body") or ""
    content = body
    if hunk:
        content = f"{hunk}\n\n{body}".strip()
    loc = f"{comment.get('path')}:{comment.get('line') or comment.get('original_line')}"
    return f"{loc}\n{content}".strip()


def _add_review_comment_events(ctx: EventContext) -> None:
    for comment in ctx.raw.get("review_comments") or []:
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
                content=_review_comment_body(comment),
                evidence=_review_comment_refs(comment),
            ),
        )


def _event_sort_key(event: dict[str, Any]) -> tuple[str, int, str]:
    rank = 50
    if event["event_type"] in {"merged", "closed"}:
        rank = 99
    return (event["timestamp"], rank, event["event_id"])


def _sort_unique_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events.sort(key=_event_sort_key)
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
