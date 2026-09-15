"""Normalize raw PR records into typed trajectory v1 objects."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .bots import extract_section, is_bot_user, strip_bot_boilerplate
from .cas import ContentAddressedStore, sha256_bytes
from .github_client import parse_repo
from .normalize import extract_patch, extract_validation, outcome_for, resolve_source_license

V1_SCHEMA_VERSION = "1.0"
COLLECTION_POLICY = "public-github-read-only"


@dataclass
class V1NormalizeOptions:
    artifact_store: ContentAddressedStore | None = None
    max_patch_bytes: int = 96 * 1024
    source_license: str | None = None


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


def _present_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any] | None:
    availability = obj.get("availability") or "missing"
    sha256 = obj.get("sha256")
    if availability != "present" or not isinstance(sha256, str) or len(sha256) != 64:
        return None
    art = {
        "id": f"obj-{index}",
        "sha256": sha256,
        "media_type": obj.get("media_type") or "application/octet-stream",
        "byte_size": int(obj.get("byte_size") or 0),
        "availability": "remote" if obj.get("uri") else "inline",
        "reproduction_role": obj.get("role") or obj.get("kind") or "git_object",
    }
    if obj.get("uri"):
        art["availability"] = "remote"
        art["uri"] = obj["uri"]
    return art


def _placeholder_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any]:
    placeholder = {
        "reason": obj.get("reason") or "missing",
        "git_oid": obj.get("git_oid"),
        "kind": obj.get("kind"),
        "availability": obj.get("availability") or "missing",
    }
    encoded = repr(placeholder).encode("utf-8")
    return {
        "id": f"obj-{index}",
        "sha256": sha256_bytes(encoded),
        "media_type": "application/json",
        "byte_size": len(encoded),
        "availability": "missing",
        "reproduction_role": obj.get("role") or obj.get("kind") or "git_object",
    }


def _artifact_from_object(obj: dict[str, Any], index: int) -> dict[str, Any]:
    present = _present_git_artifact(obj, index)
    if present:
        return present
    return _placeholder_git_artifact(obj, index)


def _cas_patch_artifact(artifact_meta: dict[str, Any], patch: str) -> tuple[str, dict[str, Any]]:
    art = {
        "id": "unified-diff",
        "sha256": artifact_meta["sha256"],
        "media_type": "text/x-diff",
        "byte_size": int(artifact_meta.get("byte_size") or len(patch.encode("utf-8"))),
        "availability": "remote",
        "reproduction_role": "implementation_patch",
        "uri": artifact_meta.get("uri") or f"cas://sha256/{artifact_meta['sha256']}",
    }
    summary = patch if patch else f"cas://sha256/{artifact_meta['sha256']}"
    return summary, art


def _inline_patch_artifact(patch: str) -> tuple[str, dict[str, Any] | None]:
    if not patch:
        return "patch not collected", None
    data = patch.encode("utf-8")
    return patch, {
        "id": "inline-patch",
        "sha256": sha256_bytes(data),
        "media_type": "text/x-diff",
        "byte_size": len(data),
        "availability": "inline",
        "reproduction_role": "implementation_patch",
        "content": patch,
    }


def _patch_artifact(raw: dict[str, Any], max_patch_bytes: int) -> tuple[str, dict[str, Any] | None]:
    patch = extract_patch(raw, max_bytes=max_patch_bytes)
    diff = raw.get("diff") or {}
    artifact_meta = diff.get("artifact") if isinstance(diff, dict) else None
    if isinstance(artifact_meta, dict) and artifact_meta.get("sha256"):
        return _cas_patch_artifact(artifact_meta, patch)
    return _inline_patch_artifact(patch)


def _text_parts(title: Any, body: Any) -> list[str]:
    parts: list[str] = []
    title_text = (title or "").strip()
    body_text = strip_bot_boilerplate(body or "")
    if title_text:
        parts.append(title_text)
    if body_text:
        parts.append(body_text)
    return parts


def _issue_statement(raw: dict[str, Any]) -> str:
    linked = raw.get("linked_issues") or []
    parts: list[str] = []
    for issue in linked:
        parts.extend(_text_parts(issue.get("title"), issue.get("body")))
    pull = raw.get("pull") or {}
    if not parts:
        parts = _text_parts(pull.get("title"), pull.get("body"))
    text = "\n\n".join(p for p in parts if p).strip()
    return text or (pull.get("title") or "untitled pull request")


def _validation_outcome(raw: dict[str, Any]) -> str:
    events = extract_validation(raw)
    if not events:
        merge = raw.get("merge_state") or {}
        if merge.get("merged"):
            return "merged without recorded checks"
        return "validation not collected"
    bits = [f"{e.get('type')}={e.get('result')}: {e.get('detail')}" for e in events]
    return "; ".join(bits)


def _software_payload(raw: dict[str, Any], patch_text: str) -> dict[str, str]:
    pull = raw.get("pull") or {}
    body = strip_bot_boilerplate(pull.get("body") or "")
    criteria = extract_section(body, ("acceptance", "criteria", "requirements")) or ""
    payload = {
        "issue_statement": _issue_statement(raw),
        "pre_change_state": str(pull.get("base_sha") or "unknown"),
        "implementation_patch": patch_text or "patch not collected",
        "validation_outcome": _validation_outcome(raw),
    }
    if criteria.strip():
        payload["acceptance_criteria"] = criteria.strip()
    return payload


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


def _completeness_score(n_events: int, pack: dict[str, Any], warnings: list[Any]) -> float:
    completeness = 0.4
    if n_events >= 3:
        completeness = 0.7
    if pack.get("complete"):
        completeness = 1.0
    elif pack.get("quarantine"):
        completeness = min(completeness, 0.5)
    if warnings:
        completeness = min(completeness, 0.8)
    return completeness


def _evidence_quality(raw: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, float]:
    pack = raw.get("snapshots") or {}
    if not isinstance(pack, dict):
        pack = {}
    warnings = (raw.get("collection_meta") or {}).get("warnings") or []
    has_review = any(e.get("event_type") in {"review", "review_comment"} for e in events)
    has_check = any(e.get("event_type") in {"check_run", "check_suite"} for e in events)
    snr = 0.5 + (0.2 if has_review else 0.0) + (0.2 if has_check else 0.0)
    repro = 1.0 if pack.get("complete") else (0.4 if pack else 0.2)
    return {
        "signal_to_noise": round(min(1.0, snr), 3),
        "reproducibility": round(repro, 3),
        "completeness": round(_completeness_score(len(events), pack, warnings), 3),
    }


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


def _pack_store_artifact(pack: dict[str, Any], store: ContentAddressedStore | None) -> dict[str, Any] | None:
    if store is None or not pack.get("pack_sha256"):
        return None
    digest = pack["pack_sha256"]
    if not store.exists(digest):
        return None
    return {
        "id": "object-pack",
        "sha256": digest,
        "media_type": "application/json",
        "byte_size": len(store.get_bytes(digest)),
        "availability": "remote",
        "reproduction_role": "object_pack",
        "uri": store.uri(digest),
    }


def _assemble_artifacts(
    raw: dict[str, Any],
    patch_art: dict[str, Any] | None,
    store: ContentAddressedStore | None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if patch_art:
        artifacts.append(patch_art)
    pack = raw.get("snapshots") or {}
    objects = pack.get("objects") or [] if isinstance(pack, dict) else []
    for index, obj in enumerate(objects):
        artifacts.append(_artifact_from_object(obj, index))
    pack_art = _pack_store_artifact(pack if isinstance(pack, dict) else {}, store)
    if pack_art:
        artifacts.append(pack_art)
    return artifacts


def _task_family(card: dict[str, Any]) -> str:
    task_family = str(card.get("trajectory_type") or "software")
    if task_family not in {"software", "research"}:
        return "software"
    return task_family


def _typed_payloads(raw: dict[str, Any], patch_text: str, task_family: str) -> dict[str, Any]:
    if task_family == "research":
        pull = raw.get("pull") or {}
        return {
            "research_payload": {
                "hypothesis": _issue_statement(raw),
                "initial_state": str(pull.get("base_sha") or "unknown"),
                "plan": strip_bot_boilerplate(pull.get("body") or "") or pull.get("title") or "unspecified",
                "measurements": _validation_outcome(raw),
            }
        }
    return {"software_payload": _software_payload(raw, patch_text)}


def _lineage(raw: dict[str, Any], source_id: str) -> dict[str, list[str]]:
    lineage: dict[str, list[str]] = {
        "supersedes": [],
        "reverts": [],
        "multi_pr_links": [],
    }
    merge = raw.get("merge_state") or {}
    if merge.get("reverted"):
        lineage["reverts"] = [source_id]
    return lineage


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

    patch_text, patch_art = _patch_artifact(raw, opts.max_patch_bytes)
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
