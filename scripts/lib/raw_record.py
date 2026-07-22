"""Assemble and write raw PR collection records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .github_client import GitHubClient, GitHubError, parse_repo
from .secrets import scan_and_sanitize_obj

CLOSES_RE = re.compile(
    r"(?i)\b(?:closes|fixes|resolves)\s+#(\d+)\b"
)
CLOSES_FULL_RE = re.compile(
    r"(?i)\b(?:closes|fixes|resolves)\s+"
    r"https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)\b"
)
CLOSES_CROSS_RE = re.compile(
    r"(?i)\b(?:closes|fixes|resolves)\s+([\w.-]+)/([\w.-]+)#(\d+)\b"
)

DEFAULT_MAX_INLINE_DIFF = 256 * 1024

# Cross-repository issue fetching allowlist (owner/repo format)
# Only repositories in this list may be fetched for cross-repo linked issues
CROSS_REPO_ALLOWLIST: tuple[str, ...] = (
    # Add approved cross-repo references here, e.g.:
    # "rmems/operation-prometheus",
)


def _user_login(obj: dict | None) -> str | None:
    if not obj:
        return None
    return obj.get("login")


def _slim_comment(c: dict) -> dict:
    user = c.get("user") or {}
    return {
        "id": c.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "created_at": c.get("created_at"),
        "body": c.get("body") or "",
        "author_association": c.get("author_association"),
    }


def _slim_review_comment(c: dict) -> dict:
    user = c.get("user") or {}
    return {
        "id": c.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "path": c.get("path"),
        "line": c.get("line") or c.get("original_line"),
        "body": c.get("body") or "",
        "diff_hunk": c.get("diff_hunk"),
        "created_at": c.get("created_at"),
        "in_reply_to_id": c.get("in_reply_to_id"),
        "author_association": c.get("author_association"),
    }


def _slim_review(r: dict) -> dict:
    user = r.get("user") or {}
    return {
        "id": r.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "state": r.get("state"),
        "body": r.get("body") or "",
        "submitted_at": r.get("submitted_at"),
    }


def _slim_commit(c: dict) -> dict:
    commit = c.get("commit") or {}
    author = commit.get("author") or {}
    return {
        "sha": c.get("sha"),
        "message": commit.get("message") or "",
        "author_login": _user_login(c.get("author")),
        "date": author.get("date"),
    }


def _slim_file(f: dict) -> dict:
    patch = f.get("patch")
    return {
        "filename": f.get("filename"),
        "status": f.get("status"),
        "additions": f.get("additions"),
        "deletions": f.get("deletions"),
        "changes": f.get("changes"),
        "patch": patch,
        "patch_truncated": patch is None and f.get("status") != "removed",
    }


def parse_linked_issue_numbers(body: str | None, default_owner: str, default_repo: str) -> list[tuple[str, str, int]]:
    """Return list of (owner, repo, number) referenced as closed by the PR body."""
    if not body:
        return []
    found: list[tuple[str, str, int]] = []
    seen: set[tuple[str, str, int]] = set()
    for m in CLOSES_RE.finditer(body):
        key = (default_owner, default_repo, int(m.group(1)))
        if key not in seen:
            seen.add(key)
            found.append(key)
    for m in CLOSES_FULL_RE.finditer(body):
        # full URL with owner/repo capture
        key = (m.group(1), m.group(2), int(m.group(3)))
        if key not in seen:
            seen.add(key)
            found.append(key)
    for m in CLOSES_CROSS_RE.finditer(body):
        key = (m.group(1), m.group(2), int(m.group(3)))
        if key not in seen:
            seen.add(key)
            found.append(key)
    return found


def collect_pr(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    *,
    include_checks: bool = True,
    include_diff: bool = True,
) -> dict[str, Any]:
    """Fetch a full raw trajectory-oriented PR record (read-only)."""
    owner, name = parse_repo(repo)
    full = f"{owner}/{name}"
    warnings: list[str] = []
    endpoints: list[str] = []

    pull = client.get_json(f"/repos/{full}/pulls/{pr_number}")
    endpoints.append("pulls")
    if not isinstance(pull, dict):
        raise GitHubError(f"Unexpected pull payload for {full}#{pr_number}")

    issue_comments = client.get_all(f"/repos/{full}/issues/{pr_number}/comments")
    endpoints.append("issue_comments")
    review_comments = client.get_all(f"/repos/{full}/pulls/{pr_number}/comments")
    endpoints.append("review_comments")
    reviews = client.get_all(f"/repos/{full}/pulls/{pr_number}/reviews")
    endpoints.append("reviews")
    commits = client.get_all(f"/repos/{full}/pulls/{pr_number}/commits")
    endpoints.append("commits")
    files = client.get_all(f"/repos/{full}/pulls/{pr_number}/files")
    endpoints.append("files")

    diff_text: str | None = None
    if include_diff:
        try:
            diff_text = client.get_text(f"/repos/{full}/pulls/{pr_number}")
            endpoints.append("diff")
        except GitHubError as exc:
            warnings.append(f"diff_fetch_failed: {exc}")

    checks: dict[str, Any] = {"check_runs": [], "combined_status": None}
    head_sha = (pull.get("head") or {}).get("sha")
    if include_checks and head_sha:
        try:
            cr = client.get_json(
                f"/repos/{full}/commits/{head_sha}/check-runs?per_page=100"
            )
            endpoints.append("check_runs")
            runs = (cr or {}).get("check_runs") or []
            checks["check_runs"] = [
                {
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "html_url": r.get("html_url"),
                }
                for r in runs
            ]
        except GitHubError as exc:
            warnings.append(f"check_runs_failed: {exc}")
        try:
            status = client.get_json(f"/repos/{full}/commits/{head_sha}/status")
            endpoints.append("combined_status")
            checks["combined_status"] = {
                "state": status.get("state"),
                "statuses": [
                    {
                        "context": s.get("context"),
                        "state": s.get("state"),
                        "description": s.get("description"),
                    }
                    for s in (status.get("statuses") or [])
                ],
            }
        except GitHubError as exc:
            warnings.append(f"combined_status_failed: {exc}")

    linked: list[dict[str, Any]] = []
    for i_owner, i_repo, num in parse_linked_issue_numbers(
        pull.get("body"), owner, name
    ):
        # Check if cross-repo fetch is allowed
        target_repo = f"{i_owner}/{i_repo}"
        source_repo = f"{owner}/{name}"
        if target_repo != source_repo:
            # Cross-repo reference - check allowlist
            if target_repo not in CROSS_REPO_ALLOWLIST:
                warnings.append(f"linked_issue_{num}_skipped: cross-repo {target_repo} not in allowlist")
                continue
        try:
            issue = client.get_json(f"/repos/{i_owner}/{i_repo}/issues/{num}")
            endpoints.append(f"issue_{num}")
            if isinstance(issue, dict) and not issue.get("pull_request"):
                linked.append(
                    {
                        "number": issue.get("number"),
                        "repo": f"{i_owner}/{i_repo}",
                        "title": issue.get("title"),
                        "body": issue.get("body") or "",
                        "state": issue.get("state"),
                        "html_url": issue.get("html_url"),
                        "closed_by_pr": True,
                    }
                )
        except GitHubError as exc:
            warnings.append(f"linked_issue_{num}_failed: {exc}")

    labels = [lb.get("name") for lb in (pull.get("labels") or []) if lb.get("name")]
    record: dict[str, Any] = {
        "schema_version": "raw_pr_record_v0",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "collector_version": __version__,
        "source": {
            "repo": full,
            "pr_number": pr_number,
            "html_url": pull.get("html_url"),
            "api_urls": {
                "pull": f"{client.base_url}/repos/{full}/pulls/{pr_number}",
            },
        },
        "pull": {
            "title": pull.get("title"),
            "body": pull.get("body") or "",
            "state": pull.get("state"),
            "merged": bool(pull.get("merged")),
            "merged_at": pull.get("merged_at"),
            "user_login": _user_login(pull.get("user")),
            "labels": labels,
            "base_sha": (pull.get("base") or {}).get("sha"),
            "head_sha": head_sha,
            "merge_commit_sha": pull.get("merge_commit_sha"),
            "additions": pull.get("additions"),
            "deletions": pull.get("deletions"),
            "changed_files": pull.get("changed_files"),
            "draft": bool(pull.get("draft")),
            "commits": pull.get("commits"),
            "comments": pull.get("comments"),
            "review_comments": pull.get("review_comments"),
        },
        "issue_comments": [_slim_comment(c) for c in issue_comments],
        "review_comments": [_slim_review_comment(c) for c in review_comments],
        "reviews": [_slim_review(r) for r in reviews],
        "commits": [_slim_commit(c) for c in commits],
        "files": [_slim_file(f) for f in files],
        "diff": {
            "inline": diff_text,
            "sidecar_path": None,
            "bytes": len(diff_text.encode("utf-8")) if diff_text else 0,
            "truncated": False,
        },
        "checks": checks,
        "linked_issues": linked,
        "collection_meta": {
            "authenticated": bool(client.token),
            "endpoints_called": endpoints,
            "warnings": warnings,
        },
    }
    record, sec_warnings = scan_and_sanitize_obj(record)
    record["collection_meta"]["warnings"].extend(sec_warnings)
    return record


def write_raw_record(
    record: dict[str, Any],
    out_dir: Path,
    *,
    max_inline_diff_bytes: int = DEFAULT_MAX_INLINE_DIFF,
) -> Path:
    """Write pr-N.json (and optional .diff sidecar). Returns path to JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pr_number = record["source"]["pr_number"]
    json_path = out_dir / f"pr-{pr_number}.json"

    diff_info = record.get("diff") or {}
    inline = diff_info.get("inline")
    if isinstance(inline, str) and len(inline.encode("utf-8")) > max_inline_diff_bytes:
        sidecar = out_dir / f"pr-{pr_number}.diff"
        sidecar.write_text(inline, encoding="utf-8")
        record = dict(record)
        record["diff"] = {
            **diff_info,
            "inline": None,
            "sidecar_path": sidecar.name,
            "bytes": len(inline.encode("utf-8")),
            "truncated": False,
        }

    json_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return json_path
