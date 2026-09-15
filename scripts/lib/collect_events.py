"""Collect extra GitHub-native events (timeline, check suites, statuses).

All calls are GET-only through ``GitHubClient``.  Missing or truncated
endpoints are recorded as warnings rather than invented as complete.
"""

from __future__ import annotations

from typing import Any

from .github_client import GitHubClient, GitHubError, _parse_next_link


def _user_login(obj: dict | None) -> str | None:
    if not obj:
        return None
    return obj.get("login")


def _is_not_found(exc: GitHubError) -> bool:
    return exc.status in (404, 410, 451)


def _paginate_wrapped(
    client: GitHubClient,
    first_url: str,
    list_key: str,
) -> tuple[list[dict[str, Any]], int | None, list[str]]:
    """Paginate a GitHub envelope ``{total_count, <list_key>: [...]}``."""
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_count: int | None = None
    next_url: str | None = first_url
    try:
        while next_url:
            payload, headers = client.get_json_with_headers(next_url)
            envelope = payload if isinstance(payload, dict) else {}
            if total_count is None:
                total_count = envelope.get("total_count")
            batch = envelope.get(list_key) or []
            items.extend(x for x in batch if isinstance(x, dict))
            next_url = _parse_next_link(headers.get("link", ""))
    except GitHubError as exc:
        warnings.append(f"{list_key}_failed: {exc}")
        return items, total_count, warnings
    if total_count is not None and total_count > len(items):
        warnings.append(
            f"{list_key}_truncated: total_count={total_count} collected={len(items)}"
        )
    return items, total_count, warnings


def _label_name(label: Any) -> Any:
    if isinstance(label, dict):
        return label.get("name")
    return label


def _timeline_source_path(event: dict[str, Any]) -> str | None:
    source = event.get("source")
    if not isinstance(source, dict):
        return None
    issue = source.get("issue")
    if not isinstance(issue, dict):
        return None
    return issue.get("html_url")


def _review_source_id(event: dict[str, Any]) -> Any:
    source = event.get("source")
    if isinstance(source, dict):
        return source.get("id")
    return None


def _slim_timeline_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    actor = event.get("actor") or event.get("user") or {}
    actor_dict = actor if isinstance(actor, dict) else None
    return {
        "id": event.get("id"),
        "event": event.get("event") or event.get("event_type"),
        "created_at": event.get("created_at") or event.get("submitted_at"),
        "actor_login": _user_login(actor_dict),
        "actor_type": (actor_dict or {}).get("type") if actor_dict else None,
        "commit_id": event.get("commit_id") or event.get("sha"),
        "commit_url": event.get("commit_url"),
        "label": _label_name(event.get("label")),
        "state": event.get("state"),
        "submitted_review_id": _review_source_id(event),
        "body": event.get("body") or event.get("message") or "",
        "source_path": _timeline_source_path(event),
    }


def collect_timeline(
    client: GitHubClient,
    full: str,
    pr_number: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recoverable issue/PR timeline events."""
    warnings: list[str] = []
    try:
        raw_events = client.get_all(f"/repos/{full}/issues/{pr_number}/timeline")
    except GitHubError as exc:
        prefix = "timeline_unavailable" if _is_not_found(exc) else "timeline_failed"
        warnings.append(f"{prefix}: {exc}")
        return [], warnings
    slim: list[dict[str, Any]] = []
    for event in raw_events:
        slim_event = _slim_timeline_event(event)
        if slim_event is not None:
            slim.append(slim_event)
    return slim, warnings


def slim_check_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
        "head_sha": run.get("head_sha"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "check_suite_id": (run.get("check_suite") or {}).get("id")
        if isinstance(run.get("check_suite"), dict)
        else run.get("check_suite_id"),
        "app_slug": ((run.get("app") or {}).get("slug") if isinstance(run.get("app"), dict) else None),
    }


def slim_check_suite(suite: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": suite.get("id"),
        "head_sha": suite.get("head_sha"),
        "status": suite.get("status"),
        "conclusion": suite.get("conclusion"),
        "created_at": suite.get("created_at"),
        "updated_at": suite.get("updated_at"),
        "app_slug": ((suite.get("app") or {}).get("slug") if isinstance(suite.get("app"), dict) else None),
        "latest_check_runs_count": suite.get("latest_check_runs_count"),
    }


def slim_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": status.get("id"),
        "context": status.get("context"),
        "state": status.get("state"),
        "description": status.get("description"),
        "target_url": status.get("target_url"),
        "created_at": status.get("created_at"),
        "updated_at": status.get("updated_at"),
        "sha": status.get("sha"),
    }


def collect_check_suites(
    client: GitHubClient,
    full: str,
    sha: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not sha:
        return [], []
    suites, _total, warnings = _paginate_wrapped(
        client,
        f"/repos/{full}/commits/{sha}/check-suites?per_page=100",
        list_key="check_suites",
    )
    return [slim_check_suite(s) for s in suites], warnings


def collect_commit_statuses(
    client: GitHubClient,
    full: str,
    sha: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not sha:
        return [], []
    warnings: list[str] = []
    try:
        raw = client.get_all(f"/repos/{full}/commits/{sha}/statuses")
    except GitHubError as exc:
        warnings.append(f"commit_statuses_failed: {exc}")
        return [], warnings
    return [slim_status(s) for s in raw if isinstance(s, dict)], warnings


def _commit_revert_markers(commits: list[dict[str, Any]]) -> list[str]:
    markers: list[str] = []
    for commit in commits:
        message = str(commit.get("message") or "")
        if message.lower().startswith("revert"):
            markers.append(f"commit:{commit.get('sha')}")
    return markers


def _timeline_revert_markers(timeline: list[dict[str, Any]]) -> list[str]:
    markers: list[str] = []
    for event in timeline:
        ev = str(event.get("event") or "")
        if ev == "reopened":
            continue
        body = str(event.get("body") or "")
        if ev == "committed" and body.lower().startswith("revert"):
            markers.append(f"timeline:{event.get('id')}")
    return markers


def _revert_markers(
    title: str,
    commits: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> list[str]:
    markers: list[str] = []
    if title.lower().startswith("revert"):
        markers.append("title")
    markers.extend(_commit_revert_markers(commits))
    markers.extend(_timeline_revert_markers(timeline))
    return markers


def detect_revert_state(
    pull: dict[str, Any],
    commits: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recover merge/close/revert disposition from collected evidence.

    Title/commit ``Revert`` prefixes mean this PR *is* a revert of other work.
    ``reverted`` is reserved for this PR's own work being undone later, which a
    single-PR collect cannot observe, so it stays false here.
    """
    title = str(pull.get("title") or "")
    merged = bool(pull.get("merged"))
    state = pull.get("state")
    closed = state == "closed" and not merged
    revert_markers = _revert_markers(title, commits, timeline)
    return {
        "merged": merged,
        "merged_at": pull.get("merged_at"),
        "closed": bool(closed or pull.get("closed_at")),
        "closed_at": pull.get("closed_at"),
        "reverted": False,
        "revert_evidence": revert_markers,
        "state": state,
    }
