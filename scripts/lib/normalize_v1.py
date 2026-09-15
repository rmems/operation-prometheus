"""Normalize raw PR records into typed trajectory v1 objects."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .bots import extract_section, is_bot_user, strip_bot_boilerplate
from .cas import ContentAddressedStore, sha256_bytes
from .github_client import parse_repo
from .normalize import extract_patch, extract_validation, outcome_for, resolve_source_license

V1_SCHEMA_VERSION = "1.0"
COLLECTION_POLICY = "public-github-read-only"


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


def _code_state(
    *,
    commit_oid: str | None = None,
    base_oid: str | None = None,
    head_oid: str | None = None,
    tree_oid: str | None = None,
    before_blob: str | None = None,
    after_blob: str | None = None,
) -> dict[str, str]:
    state = {}
    if commit_oid:
        state["commit_oid"] = str(commit_oid)
    if base_oid:
        state["base_oid"] = str(base_oid)
    if head_oid:
        state["head_oid"] = str(head_oid)
    if tree_oid:
        state["tree_oid"] = str(tree_oid)
    if before_blob:
        state["before_blob"] = str(before_blob)
    if after_blob:
        state["after_blob"] = str(after_blob)
    return state


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


def _blob_map(pack: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(pack, dict):
        return out
    for obj in pack.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        oid = obj.get("git_oid")
        if isinstance(oid, str) and oid:
            out[oid] = obj
    return out


def _artifact_from_object(obj: dict[str, Any], index: int) -> dict[str, Any] | None:
    availability = obj.get("availability") or "missing"
    sha256 = obj.get("sha256")
    if availability == "present" and isinstance(sha256, str) and len(sha256) == 64:
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
    placeholder = {
        "reason": obj.get("reason") or "missing",
        "git_oid": obj.get("git_oid"),
        "kind": obj.get("kind"),
        "availability": availability,
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


def _patch_artifact(raw: dict[str, Any], max_patch_bytes: int) -> tuple[str, dict[str, Any] | None]:
    patch = extract_patch(raw, max_bytes=max_patch_bytes)
    diff = raw.get("diff") or {}
    artifact_meta = diff.get("artifact") if isinstance(diff, dict) else None
    if isinstance(artifact_meta, dict) and artifact_meta.get("sha256"):
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


def _issue_statement(raw: dict[str, Any]) -> str:
    linked = raw.get("linked_issues") or []
    parts: list[str] = []
    for issue in linked:
        title = (issue.get("title") or "").strip()
        body = strip_bot_boilerplate(issue.get("body") or "")
        if title:
            parts.append(title)
        if body:
            parts.append(body)
    pull = raw.get("pull") or {}
    if not parts:
        title = (pull.get("title") or "").strip()
        body = strip_bot_boilerplate(pull.get("body") or "")
        if title:
            parts.append(title)
        if body:
            parts.append(body)
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


def _append_event(
    events: list[dict[str, Any]],
    *,
    event_id: str,
    timestamp: str | None,
    actor: dict[str, str],
    event_type: str,
    code_state: dict[str, str] | None = None,
    evidence: list[str] | None = None,
    disposition: str | None = None,
    content: str | None = None,
) -> None:
    ts = _utc(timestamp)
    if not ts:
        return
    event: dict[str, Any] = {
        "event_id": event_id,
        "timestamp": ts,
        "actor": actor,
        "event_type": event_type,
    }
    if code_state:
        event["code_state"] = code_state
    if evidence:
        event["evidence_references"] = evidence
    if disposition:
        event["disposition"] = disposition
    if content:
        event["content"] = content
    events.append(event)


def build_v1_events(raw: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    """Build chronological v1 events from a raw PR record."""
    pull = raw.get("pull") or {}
    base_oid = pull.get("base_sha")
    head_oid = pull.get("head_sha")
    default_state = _code_state(base_oid=base_oid, head_oid=head_oid)
    author = _actor(pull.get("user_login"), pull.get("user_type"))
    events: list[dict[str, Any]] = []

    _append_event(
        events,
        event_id=_event_id("pr_opened", source_id, pull.get("created_at") or pull.get("title")),
        timestamp=pull.get("created_at") or pull.get("updated_at") or pull.get("merged_at"),
        actor=author,
        event_type="issue_opened" if not pull.get("created_at") else "pr_opened",
        code_state=default_state,
        content=pull.get("title") or "",
    )

    for issue in raw.get("linked_issues") or []:
        _append_event(
            events,
            event_id=_event_id("linked_issue", source_id, issue.get("number")),
            timestamp=issue.get("created_at") or pull.get("created_at"),
            actor=_actor(issue.get("user_login"), issue.get("user_type")),
            event_type="issue_opened",
            content=issue.get("title") or "",
            evidence=[issue.get("html_url")] if issue.get("html_url") else None,
        )
        for comment in issue.get("comments") or []:
            _append_event(
                events,
                event_id=_event_id("issue_comment", source_id, comment.get("id")),
                timestamp=comment.get("created_at"),
                actor=_actor(comment.get("user_login"), comment.get("user_type")),
                event_type="issue_comment",
                content=comment.get("body") or "",
            )

    for commit in raw.get("commits") or []:
        _append_event(
            events,
            event_id=_event_id("commit", source_id, commit.get("sha")),
            timestamp=commit.get("date"),
            actor=_actor(commit.get("author_login"), commit.get("author_type")),
            event_type="commit",
            code_state=_code_state(
                commit_oid=commit.get("sha"),
                base_oid=base_oid,
                head_oid=commit.get("sha") or head_oid,
                tree_oid=commit.get("tree_oid"),
            ),
            content=commit.get("message") or "",
            disposition="successful",
        )

    for comment in raw.get("issue_comments") or []:
        _append_event(
            events,
            event_id=_event_id("pr_comment", source_id, comment.get("id")),
            timestamp=comment.get("created_at"),
            actor=_actor(comment.get("user_login"), comment.get("user_type")),
            event_type="issue_comment",
            code_state=default_state,
            content=comment.get("body") or "",
        )

    for review in raw.get("reviews") or []:
        state = str(review.get("state") or "").upper()
        if state == "APPROVED":
            disp = "successful"
        elif state in {"CHANGES_REQUESTED", "DISMISSED"}:
            disp = "failed"
        else:
            disp = "neutral"
        _append_event(
            events,
            event_id=_event_id("review", source_id, review.get("id")),
            timestamp=review.get("submitted_at"),
            actor=_actor(review.get("user_login"), review.get("user_type")),
            event_type="review",
            code_state=_code_state(
                commit_oid=review.get("commit_id") or head_oid,
                base_oid=base_oid,
                head_oid=review.get("commit_id") or head_oid,
            ),
            content=review.get("body") or "",
            disposition=disp,
            evidence=[review.get("html_url")] if review.get("html_url") else None,
        )

    for comment in raw.get("review_comments") or []:
        refs = []
        if comment.get("html_url"):
            refs.append(comment["html_url"])
        if comment.get("in_reply_to_id"):
            refs.append(f"in_reply_to:{comment['in_reply_to_id']}")
        hunk = comment.get("diff_hunk") or ""
        body = comment.get("body") or ""
        content = body
        if hunk:
            content = f"{hunk}\n\n{body}".strip()
        loc = f"{comment.get('path')}:{comment.get('line') or comment.get('original_line')}"
        _append_event(
            events,
            event_id=_event_id("review_comment", source_id, comment.get("id")),
            timestamp=comment.get("created_at"),
            actor=_actor(comment.get("user_login"), comment.get("user_type")),
            event_type="review_comment",
            code_state=_code_state(
                commit_oid=comment.get("commit_id") or comment.get("original_commit_id") or head_oid,
                base_oid=base_oid,
                head_oid=comment.get("commit_id") or head_oid,
            ),
            content=f"{loc}\n{content}".strip(),
            evidence=refs or None,
        )

    checks = raw.get("checks") or {}
    for run in checks.get("check_runs") or []:
        ts = run.get("completed_at") or run.get("started_at") or pull.get("merged_at")
        _append_event(
            events,
            event_id=_event_id("check_run", source_id, run.get("id") or run.get("name")),
            timestamp=ts,
            actor=_actor(run.get("app_slug") or "github-actions", "Bot"),
            event_type="check_run",
            code_state=_code_state(
                commit_oid=run.get("head_sha") or head_oid,
                base_oid=base_oid,
                head_oid=run.get("head_sha") or head_oid,
            ),
            content=f"{run.get('name')} {run.get('status')} {run.get('conclusion')}",
            disposition=_check_disposition(run.get("conclusion"), run.get("status")),
            evidence=[run.get("html_url")] if run.get("html_url") else None,
        )
    for suite in checks.get("check_suites") or []:
        ts = suite.get("updated_at") or suite.get("created_at") or pull.get("merged_at")
        _append_event(
            events,
            event_id=_event_id("check_suite", source_id, suite.get("id")),
            timestamp=ts,
            actor=_actor(suite.get("app_slug") or "github-actions", "Bot"),
            event_type="check_suite",
            code_state=_code_state(
                commit_oid=suite.get("head_sha") or head_oid,
                base_oid=base_oid,
                head_oid=suite.get("head_sha") or head_oid,
            ),
            content=f"{suite.get('app_slug')} {suite.get('status')} {suite.get('conclusion')}",
            disposition=_check_disposition(suite.get("conclusion"), suite.get("status")),
        )
    for status in checks.get("commit_statuses") or []:
        _append_event(
            events,
            event_id=_event_id("commit_status", source_id, status.get("id") or status.get("context")),
            timestamp=status.get("updated_at") or status.get("created_at"),
            actor=_actor("github-status", "application"),
            event_type="commit_status",
            code_state=_code_state(
                commit_oid=status.get("sha") or head_oid,
                base_oid=base_oid,
                head_oid=status.get("sha") or head_oid,
            ),
            content=f"{status.get('context')}={status.get('state')}",
            disposition=_check_disposition(status.get("state"), None),
        )

    for event in raw.get("timeline") or []:
        ev = str(event.get("event") or "timeline")
        _append_event(
            events,
            event_id=_event_id("timeline", source_id, event.get("id"), ev),
            timestamp=event.get("created_at"),
            actor=_actor(event.get("actor_login"), event.get("actor_type")),
            event_type=f"timeline_{ev}",
            code_state=_code_state(
                commit_oid=event.get("commit_id") or head_oid,
                base_oid=base_oid,
                head_oid=event.get("commit_id") or head_oid,
            ),
            content=event.get("body") or ev,
            disposition="successful" if ev in {"merged", "closed"} else None,
        )

    merge = raw.get("merge_state") or {}
    if merge.get("merged") and pull.get("merged_at"):
        _append_event(
            events,
            event_id=_event_id("merged", source_id, pull.get("merged_at")),
            timestamp=pull.get("merged_at"),
            actor=author,
            event_type="merged",
            code_state=_code_state(
                commit_oid=pull.get("merge_commit_sha") or head_oid,
                base_oid=base_oid,
                head_oid=head_oid,
            ),
            disposition="reverted" if merge.get("reverted") else "successful",
        )
    elif pull.get("closed_at") and not merge.get("merged"):
        _append_event(
            events,
            event_id=_event_id("closed", source_id, pull.get("closed_at")),
            timestamp=pull.get("closed_at"),
            actor=author,
            event_type="closed",
            code_state=default_state,
            disposition="failed",
        )

    events.sort(key=lambda e: (
        e["timestamp"],
        99 if e["event_type"] in {"merged", "closed"} else 50,
        e["event_id"],
    ))
    # Deduplicate identical event_ids (resume-safe, deterministic).
    uniq: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if event["event_id"] in seen:
            continue
        seen.add(event["event_id"])
        uniq.append(event)
    return uniq


def _evidence_quality(raw: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, float]:
    pack = raw.get("snapshots") or {}
    complete = bool(pack.get("complete")) if isinstance(pack, dict) else False
    warnings = (raw.get("collection_meta") or {}).get("warnings") or []
    n_events = len(events)
    completeness = 0.4
    if n_events >= 3:
        completeness = 0.7
    if complete:
        completeness = 1.0
    elif pack.get("quarantine"):
        completeness = min(completeness, 0.5)
    if warnings:
        completeness = min(completeness, 0.8)
    has_review = any(e.get("event_type") in {"review", "review_comment"} for e in events)
    has_check = any(e.get("event_type") in {"check_run", "check_suite"} for e in events)
    snr = 0.5 + (0.2 if has_review else 0.0) + (0.2 if has_check else 0.0)
    repro = 1.0 if complete else (0.4 if pack else 0.2)
    return {
        "signal_to_noise": round(min(1.0, snr), 3),
        "reproducibility": round(repro, 3),
        "completeness": round(completeness, 3),
    }


def normalize_record_v1(
    raw: dict[str, Any],
    card: dict[str, Any] | None = None,
    *,
    artifact_store: ContentAddressedStore | None = None,
    max_patch_bytes: int = 96 * 1024,
    source_license: str | None = None,
) -> dict[str, Any]:
    """Build a schema-v1 trajectory from a raw PR record."""
    card = card or {}
    source = raw.get("source") or {}
    repo = str(source.get("repo") or card.get("source_repo") or "unknown/unknown")
    pr = int(source.get("pr_number") or 0)
    owner, name = parse_repo(repo)
    traj_id = f"{owner}-{name}-{pr}"
    source_id = source.get("html_url") or f"https://github.com/{owner}/{name}/pull/{pr}"
    pull = raw.get("pull") or {}
    license_id = source_license or resolve_source_license(source, card)

    patch_text, patch_art = _patch_artifact(raw, max_patch_bytes)
    events = build_v1_events(raw, source_id)
    if not events:
        # Frozen raw records without timestamps still need one event for schema minItems.
        _append_event(
            events,
            event_id=_event_id("pr_opened", source_id, pr),
            timestamp="1970-01-01T00:00:00Z",
            actor=_actor(pull.get("user_login"), pull.get("user_type")),
            event_type="pr_opened",
            code_state=_code_state(base_oid=pull.get("base_sha"), head_oid=pull.get("head_sha")),
            content=pull.get("title") or "undated pull request",
            disposition="inconclusive",
        )

    artifacts: list[dict[str, Any]] = []
    if patch_art:
        artifacts.append(patch_art)
    pack = raw.get("snapshots") or {}
    for index, obj in enumerate(pack.get("objects") or [] if isinstance(pack, dict) else []):
        art = _artifact_from_object(obj, index)
        if art:
            artifacts.append(art)
    if artifact_store is not None and isinstance(pack, dict) and pack.get("pack_sha256"):
        if artifact_store.exists(pack["pack_sha256"]):
            artifacts.append(
                {
                    "id": "object-pack",
                    "sha256": pack["pack_sha256"],
                    "media_type": "application/json",
                    "byte_size": len(artifact_store.get_bytes(pack["pack_sha256"])),
                    "availability": "remote",
                    "reproduction_role": "object_pack",
                    "uri": artifact_store.uri(pack["pack_sha256"]),
                }
            )

    task_family = str(card.get("trajectory_type") or "software")
    if task_family not in {"software", "research"}:
        task_family = "software"

    terminal = _terminal_disposition(raw)
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
        "terminal_disposition": terminal,
        "evidence_quality": _evidence_quality(raw, events),
        "events": events,
        "artifacts": artifacts,
        "software_payload": _software_payload(raw, patch_text),
    }
    if task_family == "research":
        record.pop("software_payload")
        record["research_payload"] = {
            "hypothesis": _issue_statement(raw),
            "initial_state": str(pull.get("base_sha") or "unknown"),
            "plan": strip_bot_boilerplate(pull.get("body") or "") or pull.get("title") or "unspecified",
            "measurements": _validation_outcome(raw),
        }
    lineage = {
        "supersedes": [],
        "reverts": [],
        "multi_pr_links": [],
    }
    merge = raw.get("merge_state") or {}
    if merge.get("reverted"):
        lineage["reverts"] = [source_id]
    record["lineage"] = lineage
    return record
